"""Semente do E2E do Explorador (ticket #19): os 6 Eventos da Tela 8 numa Integração da
Organização criada pelo teste, passando pela correlação, pelo fechamento e pelas Regras de
verdade (os mesmos módulos dos workers). Roda com `uv run python` na raiz do repositório.

Uso: seed_execution.py <nome da Organização> <nome da Integração>
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from aid_correlation_worker.close import close_idle
from aid_correlation_worker.correlate import correlate_integration
from aid_diagnosis_worker.evaluate import evaluate_execution
from aid_security.references import derive_tenant_key, reference_hmac
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

DB = os.environ.get("E2E_DB_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres")
KEY = os.environ["HMAC_MASTER_KEY"].encode()
T0 = datetime.now(UTC).replace(microsecond=120000) - timedelta(minutes=30)
SOURCE = {"provider": "gcp", "service": "sap-order-sync", "resource": "sap-order-sync"}
STEPS = [
    (0, "INFO", "outbound_message", {"trace_id": "trace-abc"}, None),
    (220, "INFO", "transform", {"execution_id": "exec-123", "trace_id": "trace-abc"}, None),
    (282, "INFO", "BAPI_SALESORDER_CREATE", {"execution_id": "exec-123"}, None),
    (
        30282,
        "ERROR",
        "BAPI_SALESORDER_CREATE",
        {"execution_id": "exec-123"},
        {"category": "TIMEOUT", "http_status": 504, "message": "UPSTREAM_TIMEOUT"},
    ),
    (30410, "WARNING", "retry_scheduled", {"execution_id": "exec-123"}, None),
    (30412, "INFO", "sap_confirmation", {"execution_id": "exec-123"}, None),
]


async def main(organization: str, integration_name: str) -> None:
    engine = create_async_engine(DB, poolclass=NullPool)
    async with engine.begin() as connection:
        found = (
            await connection.execute(
                text(
                    "select i.tenant_id::text as tenant, i.id::text as integration"
                    " from doctor.integrations i join public.organizations o on o.id = i.tenant_id"
                    " where o.name = :o and i.name = :i"
                ),
                {"o": organization, "i": integration_name},
            )
        ).one()
        reference = reference_hmac(derive_tenant_key(KEY, UUID(found.tenant)), "4500012345")
        raw = str(uuid4())
        await connection.execute(
            text(
                "insert into doctor.raw_log_objects (id, tenant_id, storage_path, sha256,"
                " size_bytes, source) values (:r, :t, :p, repeat('a', 64), 10, 'api')"
            ),
            {"r": raw, "t": found.tenant, "p": f"{found.tenant}/api/{raw}.json"},
        )
        await connection.execute(text("select doctor.ensure_event_partition(:d)"), {"d": T0.date()})
        for offset, severity, operation, ids, error in STEPS:
            event = str(uuid4())
            await connection.execute(
                text(
                    "insert into doctor.events (id, tenant_id, integration_id, raw_log_object_id,"
                    " timestamp, schema_version, source, operation, severity, error, dedup_key,"
                    " execution_id, trace_id, business_context, business_reference, attributes,"
                    " sanitization_report) values (:id, :t, :i, :r, :ts, '1.0',"
                    " cast(:src as jsonb), :op, :sev, cast(:err as jsonb), :dedup, :exec,"
                    " :trace, cast(:ctx as jsonb), :ref, cast(:attrs as jsonb),"
                    " cast(:report as jsonb))"
                ),
                {
                    "id": event,
                    "dedup": event,
                    "t": found.tenant,
                    "i": found.integration,
                    "r": raw,
                    "ts": T0 + timedelta(milliseconds=offset),
                    "src": json.dumps(SOURCE),
                    "op": operation,
                    "sev": severity,
                    "err": json.dumps(error) if error else None,
                    "exec": ids.get("execution_id"),
                    "trace": ids.get("trace_id"),
                    "ctx": json.dumps({"entity_type": "pedido", "entity_reference": reference}),
                    "ref": reference,
                    "attrs": json.dumps({"authorization": "[REMOVIDO:bearer]"}),
                    "report": json.dumps({"counts": {"bearer": 1, "referencia": 1}}),
                },
            )
    await correlate_integration(engine, {"integration_id": found.integration})
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "update doctor.executions set last_activity_at = now() - interval '6 minutes'"
                " where integration_id = cast(:i as uuid)"
            ),
            {"i": found.integration},
        )
    await close_idle(engine)
    async with engine.begin() as connection:
        execution = await connection.scalar(
            text(
                "select id::text from doctor.executions where integration_id = cast(:i as uuid)"
                " and merged_into is null"
            ),
            {"i": found.integration},
        )
    await evaluate_execution(engine, {"execution_id": execution})
    await engine.dispose()
    print(execution)  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
