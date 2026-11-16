"""Regras de Sanitização da Organização pela API (#13): todo Papel lê, Owner e Admin com MFA
mudam, e um padrão que travaria ou não compila é recusado antes de chegar ao worker."""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aid_api.core.auth import Claims, get_claims
from aid_api.main import create_app
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
    ids = {"tenant": str(uuid4()), "admin": str(uuid4()), "analyst": str(uuid4())}
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values"
            " (:a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :ea),"
            " (:n, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :en)",
            "insert into public.organizations (id, name, slug) values (:t, 'Regras', :s)",
            "insert into doctor.tenants (id) values (:t)",
            "insert into public.organization_members (org_id, user_id, role)"
            " values (:t, :a, 'member'), (:t, :n, 'member')",
            "insert into doctor.memberships (tenant_id, user_id, role)"
            " values (:t, :a, 'admin'), (:t, :n, 'analyst')",
        ):
            await connection.execute(
                text(sql),
                {
                    "t": ids["tenant"],
                    "a": ids["admin"],
                    "n": ids["analyst"],
                    "s": f"regras-{ids['tenant'][:8]}",
                    "ea": f"{ids['admin']}@a.test",
                    "en": f"{ids['analyst']}@a.test",
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
            text("delete from auth.users where id in (:a, :n)"),
            {"a": ids["admin"], "n": ids["analyst"]},
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


@pytest.mark.asyncio
async def test_gestor_configura_os_padroes_e_todo_papel_le(
    engine: AsyncEngine, org: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://api.test",
        headers={"authorization": "Bearer jwt"},
    ) as client:
        app.dependency_overrides[get_claims] = lambda: claims(
            org["analyst"], org["tenant"], "analyst"
        )
        default = await client.get("/api/v1/privacy/sanitization")
        assert default.json() == {
            "extra_patterns": {},
            "detect_ips": True,
            "allow_private_ips": False,
        }
        body = {
            "extra_patterns": {"matricula": "MAT-[0-9]{6}"},
            "detect_ips": True,
            "allow_private_ips": True,
        }
        refused = await client.put("/api/v1/privacy/sanitization", json=body)
        assert refused.status_code == 403

        app.dependency_overrides[get_claims] = lambda: claims(
            org["admin"], org["tenant"], "admin", "aal1"
        )
        assert (await client.put("/api/v1/privacy/sanitization", json=body)).status_code == 403

        app.dependency_overrides[get_claims] = lambda: claims(org["admin"], org["tenant"], "admin")
        for bad, why in (
            ({"ruim": "([a-z"}, "não compila"),
            ({"lento": "(a+)+$"}, "quantificador aninhado"),
            ({"vazio": "x*"}, "casa com texto vazio"),
            ({"Tipo Ruim": "MAT"}, "tipo fora do formato"),
        ):
            response = await client.put(
                "/api/v1/privacy/sanitization", json={**body, "extra_patterns": bad}
            )
            assert (response.status_code, response.json()["code"]) == (422, "validation_error"), why
        saved = await client.put("/api/v1/privacy/sanitization", json=body)
        assert saved.status_code == 200, saved.text
        assert saved.json() == body

        app.dependency_overrides[get_claims] = lambda: claims(
            org["analyst"], org["tenant"], "analyst"
        )
        assert (await client.get("/api/v1/privacy/sanitization")).json() == body
