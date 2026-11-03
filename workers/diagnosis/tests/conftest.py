"""Fixtures de banco dos testes do worker de diagnóstico (INTEGRATION_DB_URL, job de E2E do CI)."""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")


async def run(engine: AsyncEngine, sql: str, **params: object) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


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
        " environment) values (:i, :t, 'Pedidos SF → SAP', 'salesforce', 'sap', 'prd')",
        i=ids["integration"],
        t=ids["tenant"],
    )
    yield ids
    for table in (
        "knowledge_chunks",
        "knowledge_documents",
        "execution_stats_hourly",
        "incident_history",
        "incident_comments",
        "diagnoses",
        "incident_executions",
        "incidents",
        "rule_matches",
        "events",
        "execution_merges",
        "executions",
        "outbox_messages",
        "integrations",
    ):
        await run(engine, f"delete from doctor.{table} where tenant_id = :t", t=ids["tenant"])  # noqa: S608
    await run(engine, "delete from doctor.incident_counters where tenant_id = :t", t=ids["tenant"])
    await run(engine, "delete from doctor.tenants where id = :t", t=ids["tenant"])
    await run(engine, "delete from public.organizations where id = :t", t=ids["tenant"])
