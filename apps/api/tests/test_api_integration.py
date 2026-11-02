"""Contra um Postgres real. Rodam só com INTEGRATION_DB_URL, no job de E2E do CI."""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from aid_api.core.auth import Claims
from aid_api.core.db import tenant_tx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")


def claims_for(tenant_id: str, role: str = "viewer") -> Claims:
    raw = {
        "sub": str(uuid4()),
        "role": "authenticated",
        "aal": "aal1",
        "tenant_id": tenant_id,
        "tenant_role": role,
    }
    return Claims(
        sub=raw["sub"], email=None, aal="aal1", tenant_id=tenant_id, tenant_role=role, raw=raw
    )


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


@pytest_asyncio.fixture
async def tenants(engine: AsyncEngine) -> AsyncIterator[tuple[str, str]]:
    first, second = str(uuid4()), str(uuid4())
    async with engine.begin() as connection:
        for tenant in (first, second):
            await connection.execute(
                text("insert into public.organizations (id, name, slug) values (:i, 'T', :s)"),
                {"i": tenant, "s": f"t-{tenant}"[:40].rstrip("-")},
            )
            await connection.execute(
                text("insert into doctor.tenants (id) values (:i)"), {"i": tenant}
            )
    yield first, second
    async with engine.begin() as connection:
        for tenant in (first, second):
            await connection.execute(
                text("delete from doctor.tenants where id = :i"), {"i": tenant}
            )
            await connection.execute(
                text("delete from public.organizations where id = :i"), {"i": tenant}
            )


async def assert_isolated(
    engine: AsyncEngine, claims: Claims, table: str, column: str, tenant_id: str
) -> None:
    """Isolamento genérico: consulta sem filtro, e o RLS devolve só a Organização do JWT."""
    async with tenant_tx(claims, engine) as connection:
        result = await connection.execute(text(f"select {column}::text from {table}"))  # noqa: S608
        rows = list(result.scalars())
    assert rows == [tenant_id]


@pytest.mark.asyncio
async def test_rls_age_dentro_da_api_sem_filtro_de_tenant(
    engine: AsyncEngine, tenants: tuple[str, str]
) -> None:
    first, second = tenants
    await assert_isolated(engine, claims_for(first), "doctor.tenants", "id", first)
    await assert_isolated(engine, claims_for(second), "doctor.tenants", "id", second)


@pytest.mark.asyncio
async def test_rota_de_usuario_nunca_usa_service_role(
    engine: AsyncEngine, tenants: tuple[str, str]
) -> None:
    async with tenant_tx(claims_for(tenants[0]), engine) as connection:
        role = await connection.scalar(text("select current_user"))
        bypass = await connection.scalar(
            text("select rolbypassrls from pg_roles where rolname = current_user")
        )
    assert role == "authenticated"
    assert bypass is False
