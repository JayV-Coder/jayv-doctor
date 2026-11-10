"""INT-008 pelo Mapa com `reconcile` (#40): o pedido visto na origem (Salesforce) que não chegou
ao destino (SAP) na mesma Execução diverge."""

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from aid_correlation_worker.close import reconcile_due
from aid_diagnosis_worker.evaluate import evaluate_execution
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
T0 = datetime(2026, 11, 2, 14, 2, tzinfo=UTC)


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


async def scenario(
    engine: AsyncEngine, ids: dict[str, str], *, reached_sap: bool, at: datetime = T0
) -> str:
    mapping, execution = str(uuid4()), str(uuid4())
    await run(
        engine,
        "insert into doctor.correlation_mappings (id, tenant_id, integration_id, name, keys,"
        " reconcile) values (:m, :t, :i, 'Pedido', cast(:k as jsonb), true)",
        m=mapping,
        t=ids["tenant"],
        i=ids["integration"],
        k=json.dumps([{"system": "salesforce", "field": "execution_id"}]),
    )
    await run(
        engine,
        "insert into doctor.executions (id, tenant_id, integration_id, status, first_event_at,"
        " last_event_at, event_count, closed_at) values (:x, :t, :i, 'success', :a, :b, 2, now())",
        x=execution,
        t=ids["tenant"],
        i=ids["integration"],
        a=at,
        b=at + timedelta(seconds=5),
    )
    steps = [("salesforce", 0), ("gcp", 2)] + ([("sap", 5)] if reached_sap else [])
    for provider, second in steps:
        await run(
            engine,
            "insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version,"
            " source, operation, severity, dedup_key, execution_ref, correlated_by, cross_keys)"
            " values (:id, :t, :i, :at, '1.0', cast(:s as jsonb), 'op', 'INFO', :d, :x,"
            " 'cross_system', cast(:k as text[]))",
            id=str(uuid4()),
            t=ids["tenant"],
            i=ids["integration"],
            at=at + timedelta(seconds=second),
            s=json.dumps({"provider": provider, "service": provider}),
            d=str(uuid4()),
            x=execution,
            k=[f"{mapping}:801XX0001"] if provider != "gcp" else [],
        )
    return execution


async def codes(engine: AsyncEngine, execution: str) -> list[str]:
    async with engine.begin() as connection:
        found = await connection.execute(
            text("select rule_code from doctor.rule_matches where execution_id = cast(:x as uuid)"),
            {"x": execution},
        )
        return [row[0] for row in found]


@pytest.mark.asyncio
async def test_pedido_da_origem_sem_registro_no_destino_abre_int_008(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    execution = await scenario(engine, tenant, reached_sap=False)
    incident = await evaluate_execution(engine, {"execution_id": execution})
    assert incident is not None
    assert await codes(engine, execution) == ["INT-008"]


@pytest.mark.asyncio
async def test_pedido_que_chegou_ao_destino_nao_diverge(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    execution = await scenario(engine, tenant, reached_sap=True)
    assert await evaluate_execution(engine, {"execution_id": execution}) is None
    assert await codes(engine, execution) == []


@pytest.mark.asyncio
async def test_dentro_da_janela_do_mapa_o_destino_ainda_pode_chegar(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    """Fechou com 5 min sem novidade, mas a janela do Mapa (60 min) não passou: não diverge."""
    recent = datetime.now(UTC) - timedelta(minutes=10)
    async with engine.begin() as connection:
        await connection.execute(
            text("select doctor.ensure_event_partition(cast(:d as date))"), {"d": recent.date()}
        )
    execution = await scenario(engine, tenant, reached_sap=False, at=recent)
    assert await evaluate_execution(engine, {"execution_id": execution}) is None
    # A varredura só pede a reavaliação depois da janela.
    assert await reconcile_due(engine) == 0


@pytest.mark.asyncio
async def test_varredura_pede_a_reavaliacao_uma_vez_depois_da_janela(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    execution = await scenario(engine, tenant, reached_sap=False)
    assert await reconcile_due(engine) >= 1
    async with engine.begin() as connection:
        queued = await connection.scalar(
            text(
                "select count(*) from doctor.outbox_messages where topic = 'rules.evaluate'"
                " and payload ->> 'execution_id' = :x"
            ),
            {"x": execution},
        )
    assert queued == 1
    assert await reconcile_due(engine) == 0
