"""Semente do E2E da correlação entre sistemas (ticket #40): um pedido criado no Salesforce,
processado no Cloud Run e com timeout no SAP, cada sistema com o próprio id forte, ligados pelo
Mapa de identificadores. Passa pela correlação, pelo fechamento e pelas Regras de verdade.

Uso: seed_cross_system.py <nome da Organização> <nome da Integração>
Imprime o id da Execução.
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from aid_correlation_worker.close import close_idle
from aid_correlation_worker.correlate import correlate_integration
from aid_diagnosis_worker.evaluate import evaluate_execution
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

DB = os.environ.get("E2E_DB_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres")
T0 = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=30)
ORDER = "801XX0001"
KEYS = [
    {"system": "salesforce", "field": "execution_id"},
    {
        "system": "gcp",
        "field": "attributes.sf_order",
        "transforms": [{"op": "strip_prefix", "value": "SF-"}],
    },
    {"system": "sap", "field": "attributes.bstkd", "transforms": [{"op": "strip_leading_zeros"}]},
]
STEPS = [
    (0, "salesforce", "Order.afterInsert", "INFO", {"execution_id": ORDER}, {}, None),
    (
        900,
        "gcp",
        "order-router",
        "INFO",
        {"trace_id": "trace-gcp-9"},
        {"sf_order": f"SF-{ORDER}"},
        None,
    ),
    (
        31_000,
        "sap",
        "BAPI_SALESORDER_CREATE",
        "ERROR",
        {"execution_id": "IDOC-77"},
        {"bstkd": f"0000{ORDER}"},
        {"category": "TIMEOUT", "http_status": 504, "message": "Tempo esgotado no SAP"},
    ),
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
        await connection.execute(
            text(
                "insert into doctor.correlation_mappings (tenant_id, integration_id, name, keys)"
                " values (cast(:t as uuid), cast(:i as uuid), 'Pedido', cast(:k as jsonb))"
            ),
            {"t": found.tenant, "i": found.integration, "k": json.dumps(KEYS)},
        )
        await connection.execute(text("select doctor.ensure_event_partition(:d)"), {"d": T0.date()})
        for offset, provider, operation, severity, ids, attributes, error in STEPS:
            event = str(uuid4())
            await connection.execute(
                text(
                    "insert into doctor.events (id, tenant_id, integration_id, timestamp,"
                    " schema_version, source, operation, severity, error, dedup_key,"
                    " execution_id, trace_id, attributes) values (:id, :t, :i, :ts, '1.0',"
                    " cast(:src as jsonb), :op, :sev, cast(:err as jsonb), :dedup, :exec, :trace,"
                    " cast(:attrs as jsonb))"
                ),
                {
                    "id": event,
                    "dedup": event,
                    "t": found.tenant,
                    "i": found.integration,
                    "ts": T0 + timedelta(milliseconds=offset),
                    "src": json.dumps({"provider": provider, "service": operation.split(".")[0]}),
                    "op": operation,
                    "sev": severity,
                    "err": json.dumps(error) if error else None,
                    "exec": ids.get("execution_id"),
                    "trace": ids.get("trace_id"),
                    "attrs": json.dumps(attributes),
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
