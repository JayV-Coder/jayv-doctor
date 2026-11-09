"""Coletas autorizadas pela Organização (a config vem da plataforma, validada lá).

Cada registro vira Evento no contrato, com `event_id` estável (o mesmo registro lido de novo dá
o mesmo id) e Sanitização local antes de ir para a fila: segredos e dados pessoais não saem da
rede do cliente. A Referência de negócio vira HMAC na plataforma, que tem a chave.
"""

import hashlib
import json
import os
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from aid_connectors.base import stable_uuid7
from aid_contracts.events import EventValidationError, validate_event
from aid_ingestion.cleaning import EventSanitizer
from aid_ingestion.mapping import RejectedLineError, to_event
from aid_ingestion.parsing import read_records

from aid_agent.buffer import Buffer

SOURCE = {"provider": "sap", "service": "agent"}
IDOC_ERRORS = {"51", "56", "63", "65", "66", "69"}
# A mesma Sanitização da plataforma, sem a chave das Referências (a plataforma sanitiza de novo).
LOCAL = EventSanitizer()


def sanitize(event: dict[str, Any]) -> dict[str, Any]:
    return LOCAL(event)[0]


def sap_zone() -> ZoneInfo:
    """Fuso do servidor SAP: datas e horas das tabelas e mensagens vêm no horário local dele."""
    return ZoneInfo(os.environ.get("AID_SAP_TIMEZONE", "UTC"))


def stable_event_id(key: str, at: str) -> str:
    return stable_uuid7(f"aid-agent:{key}", datetime.fromisoformat(at))


def enqueue(buffer: Buffer, events: list[dict[str, Any]]) -> int:
    valid = []
    for event in events:
        try:
            validate_event(event)
        except EventValidationError:
            continue
        valid.append(event)
    return buffer.enqueue(valid)


class DirectoryCollector:
    """Arquivos de exportação (SM58, SLG1, status de IDoc, NDJSON no contrato) numa pasta. Um
    arquivo novo ou mudado (tamanho ou data) é lido inteiro. O `event_id` vem do nome do arquivo
    e do conteúdo do registro, não da linha: regravar, acrescentar ou reordenar não duplica, e a
    fila não enfileira de novo o que já foi enviado."""

    def __init__(self, spec: Mapping[str, Any], integration_id: str, buffer: Buffer) -> None:
        self.folder = Path(str(spec["path"]))
        self.pattern = str(spec.get("pattern", "*.csv"))
        self.format = str(spec.get("format", "csv"))
        self.integration_id = integration_id
        self.buffer = buffer

    def collect(self) -> int:
        added = 0
        if not self.folder.is_dir():
            return 0
        for file in sorted(self.folder.glob(self.pattern)):
            if not file.is_file():
                continue
            stat = file.stat()
            key = f"dir:{file}"
            mark = {"size": stat.st_size, "mtime": stat.st_mtime}
            if json.loads(self.buffer.checkpoint(key) or "{}") == mark:
                continue
            events, seen = [], Counter[str]()
            for line in read_records(file.read_bytes(), self.format):
                if line.record is None:
                    continue
                try:
                    mapped = to_event(line.record, self.integration_id, SOURCE)
                except RejectedLineError:
                    continue
                digest = hashlib.sha256(
                    json.dumps(line.record, sort_keys=True, default=str).encode()
                ).hexdigest()[:24]
                # Registros idênticos no mesmo arquivo continuam distintos pela ocorrência.
                seen[digest] += 1
                mapped["event_id"] = stable_event_id(
                    f"{file.name}:{digest}:{seen[digest]}", mapped["timestamp"]
                )
                events.append(sanitize(mapped))
            added += enqueue(self.buffer, events)
            self.buffer.save_checkpoint(key, json.dumps(mark))
        return added


class RfcConnection(Protocol):
    def call(self, function: str, **parameters: Any) -> Mapping[str, Any]: ...


def sap_moment(date: str, time: str) -> str:
    local = datetime.strptime(f"{date}{time}", "%Y%m%d%H%M%S").replace(tzinfo=sap_zone())
    return local.astimezone(UTC).isoformat()


# Páginas por rodada: o resto fica para a próxima, a partir do cursor salvo.
MAX_PAGES = 20


class RfcTableCollector:
    """Tabelas de IDoc via RFC_READ_TABLE, só da allowlist (EDIDC, EDIDS).

    O filtro usa só a marca de data e hora salva (dígitos), nunca texto da config: lê o que
    mudou desde a marca, em páginas de `max_rows` (`ROWSKIPS`). Se a rodada não chega ao fim, o
    cursor (marca e páginas lidas) fica salvo e a próxima continua dele; a marca só avança quando
    a leitura termina. Linhas relidas não duplicam: a fila ignora o que já foi enviado."""

    def __init__(
        self,
        spec: Mapping[str, Any],
        integration_id: str,
        buffer: Buffer,
        connect: Callable[[], RfcConnection],
    ) -> None:
        self.table = str(spec["table"])
        self.fields = [str(field) for field in spec["fields"]]
        self.max_rows = int(spec.get("max_rows", 1000))
        self.integration_id = integration_id
        self.buffer = buffer
        self.connect = connect
        self.date_field, self.time_field = (
            ("LOGDAT", "LOGTIM") if self.table == "EDIDS" else ("UPDDAT", "UPDTIM")
        )

    def cursor(self) -> tuple[str, int]:
        found = json.loads(self.buffer.checkpoint(f"rfc_table:{self.table}") or "{}")
        since = str(found.get("since", ""))
        if not since.isdigit() or len(since) != 14:
            since = datetime.now(sap_zone()).strftime("%Y%m%d000000")
        return since, int(found.get("skip", 0))

    def options(self, since: str) -> list[dict[str, str]]:
        day, time = since[:8], since[8:]
        # Uma condição por linha: cada linha de OPTIONS tem até 72 caracteres.
        return [
            {"TEXT": f"{self.date_field} > '{day}'"},
            {"TEXT": f"OR ( {self.date_field} = '{day}'"},
            {"TEXT": f"AND {self.time_field} >= '{time}' )"},
        ]

    def collect(self) -> int:
        since, skip = self.cursor()
        connection = self.connect()
        added, newest, finished = 0, since, False
        for _ in range(MAX_PAGES):
            found = connection.call(
                "RFC_READ_TABLE",
                QUERY_TABLE=self.table,
                DELIMITER="|",
                ROWCOUNT=self.max_rows,
                ROWSKIPS=skip,
                FIELDS=[{"FIELDNAME": field} for field in self.fields],
                OPTIONS=self.options(since),
            )
            rows = list(found.get("DATA", []))
            events = []
            for row in rows:
                parts = (part.strip() for part in str(row.get("WA", "")).split("|"))
                values = dict(zip(self.fields, parts, strict=False))
                event = self.to_event(values)
                if event is None:
                    continue
                events.append(sanitize(event))
                stamp = values.get(self.date_field, "") + values.get(self.time_field, "")
                if stamp.isdigit() and len(stamp) == 14:
                    newest = max(newest, stamp)
            added += enqueue(self.buffer, events)
            skip += len(rows)
            if len(rows) < self.max_rows:
                finished = True
                break
        cursor = {"since": newest, "skip": 0} if finished else {"since": since, "skip": skip}
        self.buffer.save_checkpoint(f"rfc_table:{self.table}", json.dumps(cursor))
        return added

    def to_event(self, row: Mapping[str, str]) -> dict[str, Any] | None:
        status = row.get("STATUS", "").lstrip("0") or "0"
        if self.table == "EDIDS":
            date, time, unique = (
                row.get("LOGDAT", ""),
                row.get("LOGTIM", ""),
                f"{row.get('DOCNUM')}:{row.get('COUNTR')}",
            )
            message = row.get("STATXT", "")
        else:
            date, time, unique = (
                row.get("UPDDAT", ""),
                row.get("UPDTIM", ""),
                f"{row.get('DOCNUM')}:{status}",
            )
            message = f"IDoc {row.get('MESTYP', '')} em status {status}"
        try:
            at = sap_moment(date, time)
        except ValueError:
            return None
        failed = status in IDOC_ERRORS
        event: dict[str, Any] = {
            "schema_version": "1.0",
            "event_id": stable_event_id(f"{self.table}:{unique}", at),
            "integration_id": self.integration_id,
            "timestamp": at,
            "source": {"provider": "sap", "service": "agent", "resource": self.table},
            "operation": (row.get("MESTYP") or f"IDoc {self.table}")[:128],
            "severity": "ERROR" if failed else "INFO",
            "execution_id": row.get("DOCNUM") or unique,
            "attributes": {"idoc_status": status, "sap_message": message[:200]},
        }
        if failed:
            event["error"] = {
                "category": "UNKNOWN",
                "code": f"IDOC {status}",
                "message": message[:8192],
            }
        return event


class RfcFunctionCollector:
    """Função customizada de leitura (`Z_AID_…`, ex.: SLG1, SM58), com o contrato:
    `IV_SINCE` (AAAAMMDDhhmmss) e a tabela `ET_MESSAGES` com TIMESTAMP, TYPE, ID, NUMBER,
    MESSAGE, OBJECT e EXTERNAL_ID (docs/operations/agente.md)."""

    def __init__(
        self,
        spec: Mapping[str, Any],
        integration_id: str,
        buffer: Buffer,
        connect: Callable[[], RfcConnection],
    ) -> None:
        self.name = str(spec["name"])
        self.integration_id = integration_id
        self.buffer = buffer
        self.connect = connect

    def collect(self) -> int:
        key = f"rfc_function:{self.name}"
        since = self.buffer.checkpoint(key) or datetime.now(sap_zone()).strftime("%Y%m%d000000")
        found = self.connect().call(self.name, IV_SINCE=since)
        events, newest = [], since
        for row in found.get("ET_MESSAGES", []):
            stamp = str(row.get("TIMESTAMP", ""))
            try:
                at = sap_moment(stamp[:8], stamp[8:])
            except ValueError:
                continue
            kind = str(row.get("TYPE", "I")).upper()[:1]
            klass, number = str(row.get("ID", "")).upper(), str(row.get("NUMBER", "")).zfill(3)
            failed = kind in ("E", "A")
            event: dict[str, Any] = {
                "schema_version": "1.0",
                "event_id": stable_event_id(
                    f"{self.name}:{stamp}:{klass}:{number}:{row.get('EXTERNAL_ID', '')}", at
                ),
                "integration_id": self.integration_id,
                "timestamp": at,
                "source": {"provider": "sap", "service": "agent", "resource": self.name},
                "operation": str(row.get("OBJECT") or self.name)[:128],
                "severity": {"A": "CRITICAL", "E": "ERROR", "W": "WARNING"}.get(kind, "INFO"),
                "attributes": {
                    "sap_message_type": kind,
                    "sap_message_id": klass,
                    "sap_message_number": number,
                },
            }
            if row.get("EXTERNAL_ID"):
                event["execution_id"] = str(row["EXTERNAL_ID"])[:256]
            if failed:
                event["error"] = {
                    "category": "UNKNOWN",
                    "code": f"{klass} {number}",
                    "message": str(row.get("MESSAGE", ""))[:8192],
                }
            events.append(sanitize(event))
            newest = max(newest, stamp)
        added = enqueue(self.buffer, events)
        self.buffer.save_checkpoint(key, newest)
        return added
