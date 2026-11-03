"""Sincronização contra Postgres real. Roda com INTEGRATION_DB_URL (job de E2E do CI)."""

import json
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from aid_connector_worker.schedule import enqueue_due
from aid_connector_worker.sync import REGISTRY, sync_connector
from aid_connectors.runtime import RetryPolicy
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
FAST = RetryPolicy(attempts=2, base_seconds=0.01, max_seconds=0.01, batch_timeout=2)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


async def one(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.begin() as connection:
        return (await connection.execute(text(sql), params)).mappings().first()


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


@pytest_asyncio.fixture
async def tenant(engine: AsyncEngine) -> AsyncIterator[dict[str, str]]:
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
    yield ids
    for table in (
        "outbox_messages",
        "ingestion_batches",
        "connector_syncs",
        "connectors",
        "integrations",
    ):
        await run(engine, f"delete from doctor.{table} where tenant_id = :t", t=ids["tenant"])  # noqa: S608
    await run(engine, "delete from doctor.tenants where id = :t", t=ids["tenant"])
    await run(engine, "delete from public.organizations where id = :t", t=ids["tenant"])


async def connector(engine: AsyncEngine, ids: dict[str, str], config: dict[str, Any]) -> str:
    connector_id = str(uuid4())
    await run(
        engine,
        "insert into doctor.connectors (id, tenant_id, integration_id, provider, name, config,"
        " secret_id) values (cast(:c as uuid), :t, :i, 'fake', 'Fake', cast(:cfg as jsonb),"
        " vault.create_secret('segredo', 'doctor/connector/' || cast(:c as text)))",
        c=connector_id,
        t=ids["tenant"],
        i=ids["integration"],
        cfg=json.dumps(config),
    )
    return connector_id


async def state(engine: AsyncEngine, connector_id: str) -> Any:
    return await one(
        engine,
        "select status, consecutive_failures, checkpoint, last_error,"
        " next_run_at > now() + interval '3 minutes' as later,"
        " (select count(*) from doctor.ingestion_batches b where b.connector_id = c.id) as batches,"
        " (select count(*) from doctor.outbox_messages o where o.topic = 'ingestion.raw'"
        "   and o.payload ->> 'batch_id' in (select id::text from doctor.ingestion_batches b"
        "   where b.connector_id = c.id)) as messages"
        " from doctor.connectors c where id = :c",
        c=connector_id,
    )


async def sync(engine: AsyncEngine, connector_id: str) -> str:
    return await sync_connector({"connector_id": connector_id}, engine, REGISTRY, FAST)


@pytest.mark.asyncio
async def test_sincronizacao_grava_lotes_checkpoint_e_reagenda(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    connector_id = await connector(engine, tenant, {"pages": 3, "page_size": 2})
    assert await sync(engine, connector_id) == "succeeded"
    current = await state(engine, connector_id)
    assert current["status"] == "active"
    assert current["checkpoint"] == {"page": 3}
    assert (current["batches"], current["messages"]) == (3, 3)
    sync_row = await one(
        engine,
        "select status, records, checkpoint_from, checkpoint_to from doctor.connector_syncs"
        " where connector_id = :c",
        c=connector_id,
    )
    assert dict(sync_row) == {
        "status": "succeeded",
        "records": 6,
        "checkpoint_from": None,
        "checkpoint_to": {"page": 3},
    }
    events = await one(
        engine,
        "select events -> 0 ->> 'integration_id' as integration from doctor.ingestion_batches"
        " where connector_id = :c limit 1",
        c=connector_id,
    )
    assert events["integration"] == tenant["integration"]


@pytest.mark.asyncio
async def test_queda_no_meio_retoma_do_ultimo_checkpoint(
    engine: AsyncEngine, tenant: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_connector_worker.sync as module

    connector_id = await connector(engine, tenant, {"pages": 4, "page_size": 1})
    original = module.store_batch
    calls = 0

    async def dying(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise KeyboardInterrupt("worker morreu")
        await original(*args, **kwargs)

    monkeypatch.setattr(module, "store_batch", dying)
    with pytest.raises(KeyboardInterrupt):
        await sync(engine, connector_id)
    assert (await state(engine, connector_id))["checkpoint"] == {"page": 2}

    monkeypatch.setattr(module, "store_batch", original)
    # A Sincronização interrompida segura a vez até o prazo vencer.
    assert await sync(engine, connector_id) == "busy"
    await run(
        engine,
        "update doctor.connector_syncs set started_at = now() - interval '1 hour'"
        " where connector_id = :c",
        c=connector_id,
    )
    assert await sync(engine, connector_id) == "succeeded"
    current = await state(engine, connector_id)
    assert (current["checkpoint"], current["batches"]) == ({"page": 4}, 4)
    interrupted = await one(
        engine,
        "select count(*) as n from doctor.connector_syncs where connector_id = :c"
        " and status = 'failed' and error = 'Sincronização interrompida'",
        c=connector_id,
    )
    assert interrupted["n"] == 1


@pytest.mark.asyncio
async def test_erro_de_autenticacao_pausa_o_conector(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    connector_id = await connector(
        engine, tenant, {"pages": 2, "fail": {"page": 1, "kind": "auth", "times": 1}}
    )
    assert await sync(engine, connector_id) == "failed"
    current = await state(engine, connector_id)
    assert current["status"] == "paused"
    assert current["last_error"] == "Credencial recusada pelo provedor (401)."
    assert await sync(engine, connector_id) == "ignored"


@pytest.mark.asyncio
async def test_tres_falhas_seguidas_marcam_failing_com_backoff(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    connector_id = await connector(
        engine, tenant, {"pages": 2, "fail": {"page": 1, "kind": "transient", "times": 99}}
    )
    for expected in (1, 2):
        assert await sync(engine, connector_id) == "failed"
        current = await state(engine, connector_id)
        assert (current["status"], current["consecutive_failures"]) == ("active", expected)
        assert not current["later"]
    assert await sync(engine, connector_id) == "failed"
    current = await state(engine, connector_id)
    assert (current["status"], current["consecutive_failures"]) == ("failing", 3)
    assert current["later"]


@pytest.mark.asyncio
async def test_agendador_enfileira_cada_conector_vencido_uma_vez(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    due = await connector(engine, tenant, {"pages": 1})
    later = await connector(engine, tenant, {"pages": 1})
    await run(
        engine,
        "update doctor.connectors set next_run_at = now() + interval '1 hour' where id = :c",
        c=later,
    )
    await enqueue_due(engine)
    await enqueue_due(engine)
    queued = await one(
        engine,
        "select array_agg(payload ->> 'connector_id') as ids from doctor.outbox_messages"
        " where topic = 'connector.sync' and tenant_id = :t",
        t=tenant["tenant"],
    )
    assert queued["ids"] == [due]
