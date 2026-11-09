"""Coletas autorizadas pela Organização (a config vem da plataforma, validada lá).

Cada registro vira Evento no contrato, com `event_id` estável (o mesmo registro lido de novo dá
o mesmo id) e Sanitização local antes de ir para a fila: segredos e dados pessoais não saem da
rede do cliente. A Referência de negócio vira HMAC na plataforma, que tem a chave.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from aid_connectors.base import stable_uuid7
from aid_contracts.events import EventValidationError, validate_event
from aid_ingestion.cleaning import fit_contract
from aid_ingestion.mapping import RejectedLineError, to_event
from aid_ingestion.parsing import read_records
from aid_security import Sanitizer

from aid_agent.buffer import Buffer

SOURCE = {"provider": "sap", "service": "agent"}
UNTOUCHED = {"schema_version", "event_id", "integration_id", "timestamp", "severity"}
IDS = ("execution_id", "trace_id")
CONTENT = Sanitizer()
IDENTIFIERS = Sanitizer(exclude_kinds=("cartao",))
IDOC_ERRORS = {"51", "56", "63", "65", "66", "69"}


def sanitize(event: dict[str, Any]) -> dict[str, Any]:
    """Sanitização local com os mesmos detectores e a mesma divisão da plataforma
    (`aid_ingestion.cleaning`), sem a chave das Referências. A plataforma sanitiza de novo."""
    content = {
        k: v for k, v in event.items() if k not in UNTOUCHED and k not in IDS and k != "source"
    }
    source = dict(event.get("source") or {})
    ids: dict[str, Any] = {k: event[k] for k in IDS if k in event}
    ids["source"] = {k: v for k, v in source.items() if k != "provider"}
    cleaned_content, _ = CONTENT.sanitize(content)
    cleaned_ids, _ = IDENTIFIERS.sanitize(ids)
    cleaned_source = {"provider": source.get("provider"), **cleaned_ids.pop("source")}
    return fit_contract({**event, **cleaned_content, **cleaned_ids, "source": cleaned_source})


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
    """Arquivos de exportação (SM58, SLG1, status de IDoc, NDJSON no contrato) numa pasta. Lê só
    o que mudou desde a última rodada; um arquivo regravado é lido de novo, e os ids estáveis
    impedem a duplicação."""

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
            mark = json.loads(self.buffer.checkpoint(key) or "{}")
            if mark.get("size") == stat.st_size and mark.get("mtime") == stat.st_mtime:
                continue
            done = int(mark.get("lines", 0)) if stat.st_size >= int(mark.get("size", 0)) else 0
            events, last = [], done
            for line in read_records(file.read_bytes(), self.format):
                last = max(last, line.number)
                if line.number <= done or line.record is None:
                    continue
                try:
                    mapped = to_event(line.record, self.integration_id, SOURCE)
                except RejectedLineError:
                    continue
                digest = hashlib.sha256(
                    json.dumps(line.record, sort_keys=True, default=str).encode()
                ).hexdigest()[:16]
                mapped["event_id"] = stable_event_id(
                    f"{file.name}:{line.number}:{digest}", mapped["timestamp"]
                )
                events.append(sanitize(mapped))
            added += enqueue(self.buffer, events)
            self.buffer.save_checkpoint(
                key, json.dumps({"size": stat.st_size, "mtime": stat.st_mtime, "lines": last})
            )
        return added


class RfcConnection(Protocol):
    def call(self, function: str, **parameters: Any) -> Mapping[str, Any]: ...


def sap_moment(date: str, time: str) -> str:
    return datetime.strptime(f"{date}{time}", "%Y%m%d%H%M%S").replace(tzinfo=UTC).isoformat()


class RfcTableCollector:
    """Tabelas de IDoc via RFC_READ_TABLE, só da allowlist (EDIDC, EDIDS). O filtro é montado só
    com a data do Checkpoint (dígitos), nunca com texto da config."""

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

    def collect(self) -> int:
        key = f"rfc_table:{self.table}"
        since = self.buffer.checkpoint(key) or datetime.now(UTC).strftime("%Y%m%d")
        if not since.isdigit() or len(since) != 8:
            since = datetime.now(UTC).strftime("%Y%m%d")
        date_field = "LOGDAT" if self.table == "EDIDS" else "UPDDAT"
        found = self.connect().call(
            "RFC_READ_TABLE",
            QUERY_TABLE=self.table,
            DELIMITER="|",
            ROWCOUNT=self.max_rows,
            FIELDS=[{"FIELDNAME": field} for field in self.fields],
            OPTIONS=[{"TEXT": f"{date_field} >= '{since}'"}],
        )
        events, newest = [], since
        for row in found.get("DATA", []):
            values = dict(
                zip(
                    self.fields,
                    (part.strip() for part in str(row.get("WA", "")).split("|")),
                    strict=False,
                )
            )
            event = self.to_event(values)
            if event is None:
                continue
            events.append(sanitize(event))
            newest = max(newest, values.get(date_field, since))
        added = enqueue(self.buffer, events)
        self.buffer.save_checkpoint(key, newest)
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
        since = self.buffer.checkpoint(key) or datetime.now(UTC).strftime("%Y%m%d000000")
        found = self.connect().call(self.name, IV_SINCE=since)
        events, newest = [], since
        for row in found.get("ET_MESSAGES", []):
            stamp = str(row.get("TIMESTAMP", ""))
            try:
                at = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC).isoformat()
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
