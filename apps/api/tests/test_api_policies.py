"""Políticas da Organização (#49): o Owner ou Admin com MFA liga o MFA obrigatório para todos os
Papéis; a partir daí, sessão sem o segundo fator recebe 403 `mfa_required`."""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aid_api.core.auth import Claims, get_claims
from aid_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


@pytest_asyncio.fixture
async def org(engine: AsyncEngine) -> AsyncIterator[dict[str, str]]:
    ids = {"tenant": str(uuid4()), "admin": str(uuid4()), "viewer": str(uuid4())}
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values"
            " (:a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :ea),"
            " (:v, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :ev)",
            "insert into public.organizations (id, name, slug) values (:t, 'Políticas', :s)",
            "insert into doctor.tenants (id) values (:t)",
            "insert into public.organization_members (org_id, user_id, role)"
            " values (:t, :a, 'member'), (:t, :v, 'member')",
            "insert into doctor.memberships (tenant_id, user_id, role)"
            " values (:t, :a, 'admin'), (:t, :v, 'viewer')",
        ):
            await connection.execute(
                text(sql),
                {
                    "t": ids["tenant"],
                    "a": ids["admin"],
                    "v": ids["viewer"],
                    "s": f"pol-{ids['tenant'][:8]}",
                    "ea": f"admin-{ids['tenant'][:8]}@politicas.test",
                    "ev": f"viewer-{ids['tenant'][:8]}@politicas.test",
                },
            )
    yield ids
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from doctor.tenants where id = :t"), {"t": ids["tenant"]}
        )
        await connection.execute(
            text("delete from public.organizations where id = :t"), {"t": ids["tenant"]}
        )
        await connection.execute(
            text("delete from auth.users where id in (:a, :v)"),
            {"a": ids["admin"], "v": ids["viewer"]},
        )


def claims(user: str, tenant: str, role: str, aal: str = "aal2") -> Claims:
    raw = {
        "sub": user,
        "role": "authenticated",
        "aal": aal,
        "tenant_id": tenant,
        "tenant_role": role,
    }
    return Claims(sub=user, email=None, aal=aal, tenant_id=tenant, tenant_role=role, raw=raw)


@pytest_asyncio.fixture
async def app(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    return create_app()


async def call(
    app: FastAPI, who: Claims, method: str, path: str, body: object = None
) -> httpx.Response:
    app.dependency_overrides[get_claims] = lambda: who
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://api.test",
        headers={"authorization": "Bearer jwt", "idempotency-key": str(uuid4())},
    ) as client:
        return await client.request(method, f"/api/v1{path}", json=body)


@pytest.mark.asyncio
async def test_admin_com_mfa_liga_o_mfa_obrigatorio(app: FastAPI, org: dict[str, str]) -> None:
    admin = claims(org["admin"], org["tenant"], "admin")
    assert (await call(app, admin, "GET", "/policies")).json() == {"require_mfa": False}
    response = await call(app, admin, "PUT", "/policies", {"require_mfa": True})
    assert (response.status_code, response.json()) == (200, {"require_mfa": True})
    # A partir daí, sem o segundo fator, nada da Organização; o /me ainda responde e avisa.
    viewer = claims(org["viewer"], org["tenant"], "viewer", aal="aal1")
    refused = await call(app, viewer, "GET", "/integrations")
    assert (refused.status_code, refused.json()["code"]) == (403, "mfa_required")
    me = await call(app, viewer, "GET", "/me")
    assert (me.status_code, me.json()["mfa_required"]) == (200, True)


@pytest.mark.asyncio
async def test_sem_o_mfa_exigido_ainda_troca_de_organizacao_com_idempotency_key(
    app: FastAPI, org: dict[str, str], engine: AsyncEngine
) -> None:
    """A saída de quem não tem MFA é trocar de Organização: vale também com `Idempotency-Key`,
    que a reserva da chave não confere a Organização de que a pessoa está saindo."""
    other = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text("update doctor.tenants set require_mfa = true where id = :t"), {"t": org["tenant"]}
        )
        await connection.execute(
            text("insert into public.organizations (id, name, slug) values (:o, 'Outra', :s)"),
            {"o": other, "s": f"outra-{other[:8]}"},
        )
        await connection.execute(text("insert into doctor.tenants (id) values (:o)"), {"o": other})
        for sql in (
            "insert into public.organization_members (org_id, user_id, role)"
            " values (:o, :v, 'member')",
            "insert into doctor.memberships (tenant_id, user_id, role) values (:o, :v, 'viewer')",
        ):
            await connection.execute(text(sql), {"o": other, "v": org["viewer"]})
    try:
        viewer = claims(org["viewer"], org["tenant"], "viewer", aal="aal1")
        response = await call(app, viewer, "POST", f"/orgs/{other}/switch")
        assert response.status_code == 204
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("delete from doctor.tenants where id = :o"), {"o": other})
            await connection.execute(
                text("delete from public.organizations where id = :o"), {"o": other}
            )


@pytest.mark.asyncio
async def test_so_owner_ou_admin_com_mfa_mudam_a_politica(
    app: FastAPI, org: dict[str, str]
) -> None:
    viewer = claims(org["viewer"], org["tenant"], "viewer")
    admin_aal1 = claims(org["admin"], org["tenant"], "admin", aal="aal1")
    for who in (viewer, admin_aal1):
        response = await call(app, who, "PUT", "/policies", {"require_mfa": True})
        assert response.status_code == 403
    assert (await call(app, viewer, "GET", "/policies")).status_code == 403


@pytest.mark.asyncio
async def test_politica_rejeita_campo_desconhecido(app: FastAPI, org: dict[str, str]) -> None:
    admin = claims(org["admin"], org["tenant"], "admin")
    response = await call(app, admin, "PUT", "/policies", {"require_mfa": True, "tenant_id": "x"})
    assert response.status_code == 422
