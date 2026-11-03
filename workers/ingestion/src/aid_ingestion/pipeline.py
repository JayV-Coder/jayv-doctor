"""Importação → Eventos: lê o Log bruto, mapeia para o Contrato v1, sanitiza, deduplica e grava.

Roda como job de plataforma (`service_role`, ADR-0004): o tenant vem da própria Importação, nunca
do conteúdo. Idempotente: Importação já encerrada é ignorada; se o worker cair no meio, a nova
entrega refaz tudo depois que o prazo do primeiro vence, e o `dedup_key` impede Evento repetido.
Os contadores finais saem do banco, não da memória, para continuarem certos depois de uma queda.

Erro de infraestrutura (banco, rede) sobe e o Pub/Sub reentrega. Qualquer outro erro encerra a
Importação como `failed`: repetir não adiantaria, e ela não pode ficar presa em `processing`.
"""

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from aid_contracts.events import EventValidationError, validate_event
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_ingestion.cleaning import EventSanitizer, secrets_removed
from aid_ingestion.mapping import RejectedLineError, to_event
from aid_ingestion.parsing import Line, read_records

logger = logging.getLogger(__name__)
BATCH = 500
FINISHED = ("done", "failed", "rejected")
# Maior que o timeout do worker (300 s): antes disso, outra entrega não assume a Importação.
LEASE = timedelta(minutes=6)
UNEXPECTED = "Erro inesperado ao processar o arquivo. Importe de novo."


class BusyError(RuntimeError):
    """Outra entrega está processando a Importação, dentro do prazo: tente mais tarde."""


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


def dedup_key(tenant_id: str, payload: Mapping[str, Any], *, by_event_id: bool = False) -> str:
    """Com `by_event_id` (Eventos de sistemas externos, que trazem o próprio id): tenant, fonte e
    event_id. Sem (Importação, cujo id é gerado aqui): tenant e o conteúdo canônico."""
    if by_event_id:
        provider = payload["source"]["provider"]
        key = f"{tenant_id}|{payload['integration_id']}|{provider}|{payload['event_id']}"
        return hashlib.sha256(key.encode()).hexdigest()
    canonical = {key: value for key, value in payload.items() if key != "event_id"}
    canonical["source"] = {
        key: value for key, value in payload["source"].items() if key != "resource"
    }
    content = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{tenant_id}|{content}".encode()).hexdigest()


def event_row(
    tenant_id: str,
    integration_id: str,
    raw_log_object_id: str | None,
    payload: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    by_event_id: bool = False,
) -> dict[str, Any]:
    context = payload.get("business_context")
    return {
        "id": payload["event_id"],
        "tenant_id": tenant_id,
        "integration_id": integration_id,
        "raw_log_object_id": raw_log_object_id,
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
        "dedup_key": dedup_key(tenant_id, payload, by_event_id=by_event_id),
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
    # Sem alvo: cobre a deduplicação e também um event_id repetido com outro conteúdo, que
    # colidiria na chave primária e derrubaria o lote inteiro.
    " on conflict do nothing"
)
INSERT_REJECTION = text(
    "insert into doctor.import_rejections (tenant_id, import_id, line_number, reason)"
    " values (cast(:tenant_id as uuid), cast(:import_id as uuid), :line_number, :reason)"
)


class Importer:
    def __init__(self, engine: AsyncEngine, job: Job, master_key: bytes) -> None:
        self.engine = engine
        self.job = job
        self.sanitize = EventSanitizer(master_key, job.tenant_id)
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
            try:
                mapped = to_event(line.record, self.job.integration_id, self.source)
                payload, report = self.sanitize(mapped)
                validate_event(payload)
            except RejectedLineError as exc:
                reason = str(exc)
            except EventValidationError:
                # A mensagem do validador pode ecoar o conteúdo da linha: fica só o motivo.
                reason = "registro fora do Contrato de evento"
            else:
                self.totals.secrets += secrets_removed(report)
                batch.events.append(
                    event_row(
                        self.job.tenant_id,
                        self.job.integration_id,
                        self.job.raw_log_object_id,
                        payload,
                        report,
                    )
                )
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
        await ensure_partitions(self.engine, batch.events, self.partitions)
        async with self.engine.begin() as connection:
            await platform(connection)
            if batch.events:
                await connection.execute(INSERT_EVENT, batch.events)
            if batch.rejections:
                await connection.execute(INSERT_REJECTION, batch.rejections)
            # Progresso parcial para a tela (Realtime em imports); o número final vem do banco.
            await connection.execute(
                text(
                    "update doctor.imports set total_lines = :lines, rejected = :rejected,"
                    " processing_started_at = now() where id = cast(:id as uuid)"
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
                " i.status, i.processing_started_at > now() - cast(:lease as interval) as busy"
                " from doctor.imports i join doctor.raw_log_objects r on r.id = i.raw_log_object_id"
                " where i.id = cast(:id as uuid) for update of i"
            ),
            {"id": import_id, "lease": LEASE},
        )
        found = result.mappings().first()
        if found is None or found["status"] in FINISHED or found["status"] == "pending":
            return None
        if found["status"] == "processing" and found["busy"]:
            raise BusyError(import_id)
        await connection.execute(
            text(
                "update doctor.imports set status = 'processing', total_lines = 0, accepted = 0,"
                " rejected = 0, duplicates = 0, secrets_removed = 0, error = null,"
                " processing_started_at = now() where id = cast(:id as uuid)"
            ),
            {"id": import_id},
        )
        await connection.execute(
            text("delete from doctor.import_rejections where import_id = cast(:id as uuid)"),
            {"id": import_id},
        )
        return Job(**{key: value for key, value in found.items() if key not in ("status", "busy")})


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


async def ensure_partitions(
    engine: AsyncEngine, rows: list[dict[str, Any]], known: set[date]
) -> None:
    # As partições são em UTC: um Evento de 30/11 23:30 -03:00 é de dezembro.
    months = {row["timestamp"].astimezone(UTC).date().replace(day=1) for row in rows}
    for month in sorted(months - known):
        # Transação própria e curta: criar partição trava a tabela-mãe.
        async with engine.begin() as connection:
            await platform(connection)
            await connection.execute(
                text("select doctor.ensure_event_partition(:day)"), {"day": month}
            )
        known.add(month)


async def fail_batch(engine: AsyncEngine, batch_id: str, reason: str) -> str:
    async with engine.begin() as connection:
        await platform(connection)
        await connection.execute(
            text(
                "update doctor.ingestion_batches set failed_at = now(), error = :e"
                " where id = cast(:b as uuid)"
            ),
            {"e": reason, "b": batch_id},
        )
    return "failed"


async def process_batch(payload: Mapping[str, Any], engine: AsyncEngine, master_key: bytes) -> str:
    """Lote de POST /ingestion/events (até 500 Eventos, já validados pela API): uma transação só.
    Reentregue depois do commit, é ignorado; antes, é refeito, e o event_id impede repetição.
    Erro permanente fica registrado no lote (`failed_at`, `error`), em vez de sumir na DLQ."""
    batch_id = str(payload["batch_id"])
    try:
        return await ingest_batch(batch_id, engine, master_key)
    except Exception as exc:
        if transient(exc):
            raise
        logger.exception("ingestão: lote %s falhou", batch_id)
        return await fail_batch(engine, batch_id, "Erro inesperado ao processar o lote.")


async def ingest_batch(batch_id: str, engine: AsyncEngine, master_key: bytes) -> str:
    async with engine.begin() as connection:
        await platform(connection)
        found = (
            await connection.execute(
                text(
                    "select tenant_id::text, integration_id::text, events,"
                    " processed_at is not null or failed_at is not null as closed"
                    " from doctor.ingestion_batches where id = cast(:b as uuid)"
                ),
                {"b": batch_id},
            )
        ).first()
    if found is None or found.closed:
        return "ignored"
    sanitize = EventSanitizer(master_key, found.tenant_id)
    rows, skipped = [], 0
    for event in found.events:
        cleaned, report = sanitize(event)
        try:
            # De novo, depois da Sanitização: o lote também pode ter chegado sem passar pela API.
            validate_event(cleaned)
        except EventValidationError:
            skipped += 1
            continue
        if cleaned["integration_id"] != found.integration_id:
            skipped += 1
            continue
        rows.append(
            event_row(
                found.tenant_id, found.integration_id, None, cleaned, report, by_event_id=True
            )
        )
    await ensure_partitions(engine, rows, set())
    async with engine.begin() as connection:
        await platform(connection)
        # Trava o lote: duas entregas simultâneas não fecham o mesmo lote duas vezes.
        closed = await connection.scalar(
            text(
                "select processed_at is not null or failed_at is not null"
                " from doctor.ingestion_batches where id = cast(:b as uuid) for update"
            ),
            {"b": batch_id},
        )
        if closed:
            return "ignored"
        if rows:
            await connection.execute(INSERT_EVENT, rows)
        await connection.execute(
            text(
                "update doctor.ingestion_batches set processed_at = now(), skipped = :s"
                " where id = cast(:b as uuid)"
            ),
            {"b": batch_id, "s": skipped},
        )
        await connection.execute(
            text(
                "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                " values (cast(:t as uuid), 'correlation.requested', cast(:p as jsonb))"
            ),
            {
                "t": found.tenant_id,
                "p": json.dumps({"batch_id": batch_id, "integration_id": found.integration_id}),
            },
        )
    return "done"


def transient(exc: Exception) -> bool:
    """Falha de infraestrutura, que outra entrega pode resolver."""
    if isinstance(exc, OperationalError | httpx.HTTPError | OSError):
        return True
    return isinstance(exc, DBAPIError) and exc.connection_invalidated


async def process_import(
    payload: Mapping[str, Any], engine: AsyncEngine, store: ObjectStore, master_key: bytes
) -> str:
    """`done`, `failed` (definitivo, sem nova tentativa) ou `ignored` (já encerrada)."""
    job = await claim(engine, str(payload["import_id"]))
    if job is None:
        return "ignored"
    try:
        return await ingest(job, engine, store, master_key)
    except Exception as exc:
        if transient(exc):
            raise
        return await fail(engine, job, UNEXPECTED)


async def ingest(job: Job, engine: AsyncEngine, store: ObjectStore, master_key: bytes) -> str:
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
