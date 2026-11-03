"""Importação → Eventos: lê o Log bruto, sanitiza, mapeia para o Contrato v1, deduplica e grava.

Roda como job de plataforma (`service_role`, ADR-0004): o tenant vem da própria Importação, nunca
do conteúdo. Idempotente: Importação já encerrada é ignorada; se o worker cair no meio, a nova
entrega refaz tudo, e o `dedup_key` impede Evento repetido. Os contadores finais saem do banco,
não da memória, para continuarem certos depois de uma queda.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from aid_contracts.events import EventValidationError, validate_event
from aid_security import Sanitizer, derive_tenant_key
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_ingestion.mapping import RejectedLineError, to_event
from aid_ingestion.parsing import Line, read_records

BATCH = 500
FINISHED = ("done", "failed", "rejected")


class ObjectStore:
    async def read(self, path: str) -> bytes | None:
        """Conteúdo do objeto no bucket do Log bruto, ou `None` se não existe."""
        raise NotImplementedError


@dataclass
class Job:
    import_id: str
    tenant_id: str
    integration_id: str
    raw_log_object_id: str
    storage_path: str
    sha256: str
    file_format: str


@dataclass
class Batch:
    events: list[dict[str, Any]] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Totals:
    lines: int = 0
    valid: int = 0
    rejected: int = 0
    secrets: int = 0


async def platform(connection: AsyncConnection) -> None:
    await connection.execute(text("set local role service_role"))


def dedup_key(tenant_id: str, payload: Mapping[str, Any]) -> str:
    """Mesmo conteúdo da mesma fonte no mesmo tenant: mesma chave, seja qual for o event_id."""
    canonical = {key: value for key, value in payload.items() if key != "event_id"}
    canonical["source"] = {
        key: value for key, value in payload["source"].items() if key != "resource"
    }
    content = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{tenant_id}|{content}".encode()).hexdigest()


def event_row(job: Job, payload: Mapping[str, Any], report: Mapping[str, Any]) -> dict[str, Any]:
    context = payload.get("business_context")
    return {
        "id": payload["event_id"],
        "tenant_id": job.tenant_id,
        "integration_id": job.integration_id,
        "raw_log_object_id": job.raw_log_object_id,
        "timestamp": datetime.fromisoformat(payload["timestamp"]),
        "schema_version": payload["schema_version"],
        "execution_id": payload.get("execution_id"),
        "trace_id": payload.get("trace_id"),
        "source": json.dumps(payload["source"]),
        "operation": payload["operation"],
        "severity": payload["severity"],
        "error": json.dumps(payload["error"]) if "error" in payload else None,
        "business_context": json.dumps(context) if context else None,
        "business_reference": context.get("entity_reference") if context else None,
        "attributes": json.dumps(payload["attributes"]) if "attributes" in payload else None,
        "sanitization_report": json.dumps(report),
        "dedup_key": dedup_key(job.tenant_id, payload),
    }


INSERT_EVENT = text(
    "insert into doctor.events (id, tenant_id, integration_id, raw_log_object_id, timestamp,"
    " schema_version, execution_id, trace_id, source, operation, severity, error,"
    " business_context, business_reference, attributes, sanitization_report, dedup_key)"
    " values (cast(:id as uuid), cast(:tenant_id as uuid), cast(:integration_id as uuid),"
    " cast(:raw_log_object_id as uuid), :timestamp, :schema_version, :execution_id, :trace_id,"
    " cast(:source as jsonb), :operation, :severity, cast(:error as jsonb),"
    " cast(:business_context as jsonb), :business_reference, cast(:attributes as jsonb),"
    " cast(:sanitization_report as jsonb), :dedup_key)"
    " on conflict (tenant_id, dedup_key, timestamp) do nothing"
)
INSERT_REJECTION = text(
    "insert into doctor.import_rejections (tenant_id, import_id, line_number, reason)"
    " values (cast(:tenant_id as uuid), cast(:import_id as uuid), :line_number, :reason)"
)


class Importer:
    def __init__(self, engine: AsyncEngine, job: Job, master_key: bytes) -> None:
        self.engine = engine
        self.job = job
        self.sanitizer = Sanitizer(reference_key=derive_tenant_key(master_key, UUID(job.tenant_id)))
        self.source = {
            "provider": "manual",
            "service": "importacao",
            "resource": f"import:{job.import_id}",
        }
        self.partitions: set[date] = set()
        self.totals = Totals()

    def line(self, line: Line, batch: Batch) -> None:
        self.totals.lines += 1
        reason = line.reason
        if line.record is not None:
            record, report = self.sanitizer.sanitize(line.record)
            self.totals.secrets += sum(
                count for kind, count in report.counts.items() if kind != "referencia"
            )
            try:
                payload = to_event(record, self.job.integration_id, self.source)
                validate_event(payload)
            except RejectedLineError as exc:
                reason = str(exc)
            except EventValidationError:
                # A mensagem do validador pode ecoar o conteúdo da linha: fica só o motivo.
                reason = "registro fora do Contrato de evento"
            else:
                batch.events.append(event_row(self.job, payload, report.as_dict()))
                self.totals.valid += 1
                return
        self.totals.rejected += 1
        batch.rejections.append(
            {
                "tenant_id": self.job.tenant_id,
                "import_id": self.job.import_id,
                "line_number": line.number,
                "reason": (reason or "linha inválida")[:500],
            }
        )

    async def flush(self, batch: Batch) -> None:
        async with self.engine.begin() as connection:
            await platform(connection)
            months = {row["timestamp"].date().replace(day=1) for row in batch.events}
            for month in sorted(months - self.partitions):
                await connection.execute(
                    text("select doctor.ensure_event_partition(:day)"), {"day": month}
                )
                self.partitions.add(month)
            if batch.events:
                await connection.execute(INSERT_EVENT, batch.events)
            if batch.rejections:
                await connection.execute(INSERT_REJECTION, batch.rejections)
            # Progresso parcial para a tela (Realtime em imports); o número final vem do banco.
            await connection.execute(
                text(
                    "update doctor.imports set total_lines = :lines, rejected = :rejected"
                    " where id = cast(:id as uuid)"
                ),
                {
                    "lines": self.totals.lines,
                    "rejected": self.totals.rejected,
                    "id": self.job.import_id,
                },
            )


async def claim(engine: AsyncEngine, import_id: str) -> Job | None:
    """Marca a Importação como `processing` e devolve o trabalho; `None` se já foi encerrada."""
    async with engine.begin() as connection:
        await platform(connection)
        result = await connection.execute(
            text(
                "select i.id::text as import_id, i.tenant_id::text, i.integration_id::text,"
                " i.raw_log_object_id::text, r.storage_path, i.sha256, i.format as file_format,"
                " i.status"
                " from doctor.imports i join doctor.raw_log_objects r on r.id = i.raw_log_object_id"
                " where i.id = cast(:id as uuid) for update of i"
            ),
            {"id": import_id},
        )
        found = result.mappings().first()
        if found is None or found["status"] in FINISHED or found["status"] == "pending":
            return None
        await connection.execute(
            text(
                "update doctor.imports set status = 'processing', total_lines = 0, accepted = 0,"
                " rejected = 0, duplicates = 0, secrets_removed = 0, error = null"
                " where id = cast(:id as uuid)"
            ),
            {"id": import_id},
        )
        await connection.execute(
            text("delete from doctor.import_rejections where import_id = cast(:id as uuid)"),
            {"id": import_id},
        )
        return Job(**{key: value for key, value in found.items() if key != "status"})


async def fail(engine: AsyncEngine, job: Job, reason: str) -> str:
    async with engine.begin() as connection:
        await platform(connection)
        await connection.execute(
            text(
                "update doctor.imports set status = 'failed', error = :e"
                " where id = cast(:id as uuid)"
            ),
            {"e": reason, "id": job.import_id},
        )
    return "failed"


async def finish(engine: AsyncEngine, job: Job, totals: Totals) -> None:
    async with engine.begin() as connection:
        await platform(connection)
        accepted = await connection.scalar(
            text(
                "select count(*) from doctor.events where tenant_id = cast(:t as uuid)"
                " and raw_log_object_id = cast(:r as uuid)"
            ),
            {"t": job.tenant_id, "r": job.raw_log_object_id},
        )
        await connection.execute(
            text(
                "update doctor.imports set status = 'done', total_lines = :lines,"
                " accepted = :accepted, rejected = :rejected, duplicates = :duplicates,"
                " secrets_removed = :secrets where id = cast(:id as uuid)"
            ),
            {
                "lines": totals.lines,
                "accepted": accepted,
                "rejected": totals.rejected,
                "duplicates": max(totals.valid - int(accepted or 0), 0),
                "secrets": totals.secrets,
                "id": job.import_id,
            },
        )
        await connection.execute(
            text(
                "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                " values (cast(:t as uuid), 'correlation.requested', cast(:p as jsonb))"
            ),
            {
                "t": job.tenant_id,
                "p": json.dumps({"import_id": job.import_id, "integration_id": job.integration_id}),
            },
        )


async def process_import(
    payload: Mapping[str, Any], engine: AsyncEngine, store: ObjectStore, master_key: bytes
) -> str:
    """`done`, `failed` (definitivo, sem nova tentativa) ou `ignored` (já encerrada)."""
    job = await claim(engine, str(payload["import_id"]))
    if job is None:
        return "ignored"
    data = await store.read(job.storage_path)
    if data is None:
        return await fail(engine, job, "Log bruto não encontrado no armazenamento")
    if hashlib.sha256(data).hexdigest() != job.sha256:
        return await fail(engine, job, "Arquivo diferente do que foi enviado")

    importer = Importer(engine, job, master_key)
    batch = Batch()
    for line in read_records(data, job.file_format):
        importer.line(line, batch)
        if len(batch.events) + len(batch.rejections) >= BATCH:
            await importer.flush(batch)
            batch = Batch()
    await importer.flush(batch)
    await finish(engine, job, importer.totals)
    return "done"
