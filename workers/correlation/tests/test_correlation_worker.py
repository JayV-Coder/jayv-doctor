"""Worker de correlação contra Postgres real. Roda com INTEGRATION_DB_URL (job de E2E do CI)."""

import json
import os
import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from aid_correlation_worker import correlate as module
from aid_correlation_worker.close import close_idle
from aid_correlation_worker.correlate import correlate_integration
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
T0 = datetime(2026, 11, 2, 14, 2, 1, 120000, tzinfo=UTC)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    async with created.begin() as connection:
        await connection.execute(text("select doctor.ensure_event_partition('2026-11-02')"))
    yield created
    await created.dispose()


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


async def rows(engine: AsyncEngine, sql: str, **params: Any) -> list[Any]:
    async with engine.begin() as connection:
        return list((await connection.execute(text(sql), params)).mappings())


async def new_tenant(engine: AsyncEngine) -> dict[str, str]:
    ids = {"tenant": str(uuid4()), "integration": str(uuid4())}
    await run(
        engine,
        "insert into public.organizations (id, name, slug) values (:t, 'T', :s)",
        t=ids["tenant"],
        s=f"t-{ids['tenant'][:30]}",
    )
    await run(engine, "insert into doctor.tenants (id) values (:t)", t=ids["tenant"])
    await run(
        engine,
        "insert into doctor.integrations (id, tenant_id, name, source_system, target_system,"
        " environment) values (:i, :t, 'Pedidos', 'salesforce', 'sap', 'prd')",
        i=ids["integration"],
        t=ids["tenant"],
    )
    return ids


async def drop_tenant(engine: AsyncEngine, ids: dict[str, str]) -> None:
    for table in ("events", "execution_merges", "executions", "outbox_messages", "integrations"):
        await run(engine, f"delete from doctor.{table} where tenant_id = :t", t=ids["tenant"])  # noqa: S608
    await run(engine, "delete from doctor.tenants where id = :t", t=ids["tenant"])
    await run(engine, "delete from public.organizations where id = :t", t=ids["tenant"])


@pytest_asyncio.fixture
async def tenant(engine: AsyncEngine) -> AsyncIterator[dict[str, str]]:
    ids = await new_tenant(engine)
    yield ids
    await drop_tenant(engine, ids)


async def insert(
    engine: AsyncEngine, ids: dict[str, str], offset_ms: int, severity: str = "INFO", **fields: Any
) -> str:
    event_id = str(uuid4())
    await run(
        engine,
        "insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version,"
        " source, operation, severity, dedup_key, execution_id, trace_id, business_reference,"
        " attributes) values (:id, :t, :i, :ts, '1.0', cast(:src as jsonb), :op, :sev, :d,"
        " :exec, :trace, :ref, cast(:attrs as jsonb))",
        id=event_id,
        t=ids["tenant"],
        i=ids["integration"],
        ts=T0 + timedelta(milliseconds=offset_ms),
        src=json.dumps({"provider": "gcp", "service": "s", "resource": fields.get("resource")}),
        op=fields.get("operation", "op"),
        sev=severity,
        d=event_id,
        exec=fields.get("execution_id"),
        trace=fields.get("trace_id"),
        ref=fields.get("business_reference"),
        attrs=json.dumps({"attempt": fields["attempt"]} if "attempt" in fields else {}),
    )
    return event_id


async def correlate(engine: AsyncEngine, ids: dict[str, str]) -> int:
    return await correlate_integration(engine, {"integration_id": ids["integration"]})


async def executions(engine: AsyncEngine, ids: dict[str, str]) -> list[Any]:
    return await rows(
        engine,
        "select id::text, status, event_count, duration_ms, correlation_keys, low_confidence,"
        " closed_at from doctor.executions where tenant_id = :t order by first_event_at",
        t=ids["tenant"],
    )


MOCKUP: list[tuple[int, str, dict[str, Any]]] = [
    (0, "INFO", {"trace_id": "trace-abc"}),
    (220, "INFO", {"execution_id": "exec-123", "trace_id": "trace-abc"}),
    (282, "INFO", {"execution_id": "exec-123"}),
    (30282, "ERROR", {"execution_id": "exec-123"}),
    (30410, "WARNING", {"execution_id": "exec-123"}),
    (30412, "INFO", {"execution_id": "exec-123"}),
]


@pytest.mark.asyncio
async def test_seis_eventos_do_mockup_em_dois_lotes_fora_de_ordem(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    shuffled = MOCKUP[:]
    random.Random(3).shuffle(shuffled)  # noqa: S311 - ordem de teste
    for offset, severity, fields in shuffled[:3]:
        await insert(engine, tenant, offset, severity, **fields)
    await correlate(engine, tenant)
    for offset, severity, fields in shuffled[3:]:
        await insert(engine, tenant, offset, severity, **fields)
    assert await correlate(engine, tenant) == 3

    (execution,) = await executions(engine, tenant)
    assert execution["event_count"] == 6
    assert execution["status"] == "failed"
    assert execution["duration_ms"] == 30412
    assert execution["correlation_keys"]["trace_id"] == ["trace-abc"]
    linked = await rows(
        engine,
        "select count(*) as n from doctor.events where tenant_id = :t and execution_ref = :x",
        t=tenant["tenant"],
        x=execution["id"],
    )
    assert linked[0]["n"] == 6
    # Mensagem repetida: nada pendente, nada muda.
    assert await correlate(engine, tenant) == 0


@pytest.mark.asyncio
async def test_referencia_de_negocio_associa_quem_chega_depois(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    await insert(engine, tenant, 0, execution_id="exec-1", business_reference="hmac:9a7b")
    await correlate(engine, tenant)
    late = await insert(engine, tenant, 120_000, business_reference="hmac:9a7b")
    await correlate(engine, tenant)
    (execution,) = await executions(engine, tenant)
    found = await rows(
        engine,
        "select correlated_by, execution_ref::text as x from doctor.events where id = :e",
        e=late,
    )
    assert found[0]["correlated_by"] == "business_reference"
    assert found[0]["x"] == execution["id"]


@pytest.mark.asyncio
async def test_trace_que_chega_depois_funde_e_guarda_o_historico(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    await insert(engine, tenant, 0, execution_id="exec-1")
    await insert(engine, tenant, 100, execution_id="exec-2")
    await correlate(engine, tenant)
    first, second = await executions(engine, tenant)
    await insert(engine, tenant, 200, execution_id="exec-2", trace_id="t-9")
    await insert(engine, tenant, 300, execution_id="exec-1", trace_id="t-9")
    await correlate(engine, tenant)
    (merged,) = await executions(engine, tenant)
    assert merged["id"] == first["id"]
    assert merged["event_count"] == 4
    history = await rows(
        engine,
        "select survivor_id::text as s, merged_id::text as m, merged_keys as k"
        " from doctor.execution_merges where tenant_id = :t",
        t=tenant["tenant"],
    )
    assert [(h["s"], h["m"]) for h in history] == [(first["id"], second["id"])]
    assert history[0]["k"]["execution_id"] == ["exec-2"]


@pytest.mark.asyncio
async def test_mesmo_trace_em_organizacoes_diferentes_fica_separado(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    other = await new_tenant(engine)
    try:
        await insert(engine, tenant, 0, trace_id="t-1")
        await insert(engine, other, 10, trace_id="t-1")
        await correlate(engine, tenant)
        await correlate(engine, other)
        (mine,) = await executions(engine, tenant)
        (theirs,) = await executions(engine, other)
        assert mine["event_count"] == theirs["event_count"] == 1
    finally:
        await drop_tenant(engine, other)


@pytest.mark.asyncio
async def test_fecha_parada_ha_5_min_e_pede_as_regras(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    await insert(engine, tenant, 0, execution_id="ok")
    await insert(engine, tenant, 10_000, "ERROR", execution_id="falha")
    await insert(engine, tenant, 20_000, resource="svc", attempt=1)
    await insert(engine, tenant, 21_000, resource="svc", attempt=2)
    await correlate(engine, tenant)
    assert {e["status"] for e in await executions(engine, tenant)} == {
        "pending_confirmation",
        "failed",
    }
    await close_idle(engine)  # ainda dentro dos 5 min: nada fecha
    assert all(e["closed_at"] is None for e in await executions(engine, tenant))

    await run(
        engine,
        "update doctor.executions set last_activity_at = now() - interval '6 minutes'"
        " where tenant_id = :t",
        t=tenant["tenant"],
    )
    await close_idle(engine)
    closed = await executions(engine, tenant)
    assert [e["status"] for e in closed] == ["success", "failed", "unknown"]
    assert closed[2]["low_confidence"] is True
    queued = await rows(
        engine,
        "select payload from doctor.outbox_messages"
        " where tenant_id = :t and topic = 'rules.evaluate'",
        t=tenant["tenant"],
    )
    assert {q["payload"]["execution_id"] for q in queued} == {e["id"] for e in closed}


@pytest.mark.asyncio
async def test_evento_tardio_reabre_a_execucao_fechada(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    await insert(engine, tenant, 0, execution_id="exec-1")
    await correlate(engine, tenant)
    await run(
        engine,
        "update doctor.executions set last_activity_at = now() - interval '6 minutes'"
        " where tenant_id = :t",
        t=tenant["tenant"],
    )
    await close_idle(engine)
    await insert(engine, tenant, 5_000, "ERROR", execution_id="exec-1")
    await correlate(engine, tenant)
    (execution,) = await executions(engine, tenant)
    assert execution["closed_at"] is None
    assert execution["status"] == "failed"
    assert execution["event_count"] == 2


@pytest.mark.asyncio
async def test_muitos_pendentes_pedem_continuacao(
    engine: AsyncEngine, tenant: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "PAGE", 2)
    for offset in range(3):
        await insert(engine, tenant, offset * 1000, execution_id=f"e-{offset}")
    assert await correlate(engine, tenant) == 2
    queued = await rows(
        engine,
        "select payload from doctor.outbox_messages"
        " where tenant_id = :t and topic = 'correlation.requested'",
        t=tenant["tenant"],
    )
    assert queued == [{"payload": {"integration_id": tenant["integration"]}}]
    assert await correlate(engine, tenant) == 1
