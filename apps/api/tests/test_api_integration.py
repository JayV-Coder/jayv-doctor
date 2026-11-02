"""Contra um Postgres real. Rodam só com INTEGRATION_DB_URL, no job de E2E do CI."""

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from aid_api.core.auth import Claims
from aid_api.core.db import tenant_tx
from aid_api.core.errors import ApiError
from aid_api.core.idempotency import IdempotencyStore
from aid_api.integrations.repo import IntegrationRepository
from aid_api.integrations.schemas import NewIntegration
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")


def claims_for(tenant_id: str, user_id: str, role: str = "viewer", aal: str = "aal1") -> Claims:
    raw = {
        "sub": user_id,
        "role": "authenticated",
        "aal": aal,
        "tenant_id": tenant_id,
        "tenant_role": role,
    }
    return Claims(
        sub=raw["sub"], email=None, aal=aal, tenant_id=tenant_id, tenant_role=role, raw=raw
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
async def user(engine: AsyncEngine) -> AsyncIterator[str]:
    user_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into auth.users (id, instance_id, aud, role, email)"
                " values (:i, '00000000-0000-0000-0000-000000000000', 'authenticated',"
                " 'authenticated', :e)"
            ),
            {"i": user_id, "e": f"{user_id}@integracao.test"},
        )
    yield user_id
    async with engine.begin() as connection:
        await connection.execute(text("delete from auth.users where id = :i"), {"i": user_id})


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
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    first, second = tenants
    await assert_isolated(engine, claims_for(first, user), "doctor.tenants", "id", first)
    await assert_isolated(engine, claims_for(second, user), "doctor.tenants", "id", second)


@pytest.mark.asyncio
async def test_rota_de_usuario_nunca_usa_service_role(
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    async with tenant_tx(claims_for(tenants[0], user), engine) as connection:
        role = await connection.scalar(text("select current_user"))
        bypass = await connection.scalar(
            text("select rolbypassrls from pg_roles where rolname = current_user")
        )
    assert role == "authenticated"
    assert bypass is False


@pytest.mark.asyncio
async def test_mesma_chave_concorrente_espera_e_devolve_a_resposta_gravada(
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    store = IdempotencyStore(engine)
    claims = claims_for(tenants[0], user)
    first_reserved = asyncio.Event()
    release_first = asyncio.Event()

    async def first() -> None:
        async with store.session(claims) as session:
            assert await session.reserve("k", "h") is None
            first_reserved.set()
            await release_first.wait()
            await session.remember("k", 201, '{"id": "1"}')

    async def second() -> object:
        await first_reserved.wait()
        async with store.session(claims) as session:
            return await session.reserve("k", "h")

    running = asyncio.create_task(first())
    waiting = asyncio.create_task(second())
    await asyncio.sleep(0.3)
    assert not waiting.done(), "a segunda chamada precisa esperar a primeira"
    release_first.set()
    await running
    stored = await waiting
    assert stored is not None
    assert stored.status == 201  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_chave_de_requisicao_que_falhou_fica_livre(
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    store = IdempotencyStore(engine)
    claims = claims_for(tenants[0], user)

    async def failing_request() -> None:
        async with store.session(claims) as session:
            await session.reserve("k2", "h")
            raise RuntimeError

    with pytest.raises(RuntimeError):
        await failing_request()
    async with store.session(claims) as session:
        assert await session.reserve("k2", "h") is None


async def add_admin(engine: AsyncEngine, tenant_id: str, user_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into public.organization_members (org_id, user_id, role)"
                " values (:t, :u, 'member')"
            ),
            {"t": tenant_id, "u": user_id},
        )
        await connection.execute(
            text(
                "insert into doctor.memberships (tenant_id, user_id, role) values (:t, :u, 'admin')"
            ),
            {"t": tenant_id, "u": user_id},
        )


@pytest.mark.asyncio
async def test_integracoes_isoladas_com_nome_unico_por_organizacao(
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    first, second = tenants
    for tenant in tenants:
        await add_admin(engine, tenant, user)
    repository = IntegrationRepository(engine)
    new = NewIntegration(
        name="Pedidos Salesforce → SAP",
        source_system="salesforce",
        target_system="sap",
        environment="prd",
    )
    acme = claims_for(first, user, "admin", "aal2")
    varejo = claims_for(second, user, "admin", "aal2")

    created = await repository.create(acme, new)
    with pytest.raises(ApiError) as duplicated:
        await repository.create(acme, new)
    assert duplicated.value.code == "integration_exists"

    assert await repository.list(varejo, include_archived=True) == []
    await repository.create(varejo, new)
    with pytest.raises(ApiError) as foreign:
        await repository.archive(varejo, created.id)
    assert foreign.value.status == 404

    archived = await repository.archive(acme, created.id)
    assert archived.archived_at is not None
    assert await repository.list(acme, include_archived=False) == []
    assert [item.id for item in await repository.list(acme, include_archived=True)] == [created.id]
