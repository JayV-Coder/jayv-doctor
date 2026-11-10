"""Mapas de identificadores (#40): validação, Papel e ciclo de vida pela API."""

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

KEYS = [
    {"system": "salesforce", "field": "execution_id"},
    {"system": "sap", "field": "attributes.bstkd", "transforms": [{"op": "strip_leading_zeros"}]},
]


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


@pytest.mark.asyncio
async def test_admin_cria_altera_e_remove_e_analyst_so_le(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    tenant, integration, admin, analyst, connector = (str(uuid4()) for _ in range(5))
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values"
            " (:a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',"
            " :ea), (:n, '00000000-0000-0000-0000-000000000000', 'authenticated',"
            " 'authenticated', :en)",
            "insert into public.organizations (id, name, slug) values (:t, 'Mapa', :s)",
            "insert into doctor.tenants (id) values (:t)",
            "insert into public.organization_members (org_id, user_id, role)"
            " values (:t, :a, 'member'), (:t, :n, 'member')",
            "insert into doctor.memberships (tenant_id, user_id, role)"
            " values (:t, :a, 'admin'), (:t, :n, 'analyst')",
            "insert into doctor.integrations (id, tenant_id, name, source_system, target_system,"
            " environment) values (:i, :t, 'Pedidos', 'salesforce', 'sap', 'prd')",
            "insert into doctor.connectors (id, tenant_id, integration_id, provider, name, config)"
            " values (:c, :t, :i, 'gcp', 'GCP', '{}')",
        ):
            await connection.execute(
                text(sql),
                {
                    "t": tenant,
                    "i": integration,
                    "a": admin,
                    "n": analyst,
                    "c": connector,
                    "s": f"mapa-{tenant[:8]}",
                    "ea": f"{admin}@a.test",
                    "en": f"{analyst}@a.test",
                },
            )

    def as_role(user: str, role: str) -> Claims:
        raw = {
            "sub": user,
            "role": "authenticated",
            "aal": "aal2",
            "tenant_id": tenant,
            "tenant_role": role,
        }
        return Claims(sub=user, email=None, aal="aal2", tenant_id=tenant, tenant_role=role, raw=raw)

    app = create_app()
    base = f"/api/v1/integrations/{integration}/correlation-mappings"
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://api.test",
            headers={"authorization": "Bearer jwt"},
        ) as client:
            app.dependency_overrides[get_claims] = lambda: as_role(admin, "admin")
            created = await client.post(
                base, json={"name": "Pedido", "keys": KEYS, "reconcile": True}
            )
            assert created.status_code == 201, created.text
            mapping = created.json()
            assert mapping["keys"][1]["transforms"] == [{"op": "strip_leading_zeros"}]
            bad = await client.post(
                base, json={"name": "Ruim", "keys": [{"system": "sap", "field": "x"}]}
            )
            assert (bad.status_code, bad.json()["code"]) == (422, "invalid_mapping")
            # A consulta só com Conector Salesforce ou OData: o GCP não consulta registros.
            gcp = await client.post(
                base,
                json={
                    "name": "Com GCP",
                    "keys": KEYS,
                    "lookup": {"connector_id": connector, "entity": "Order", "field": "Id"},
                },
            )
            assert (gcp.status_code, gcp.json()["code"]) == (422, "invalid_mapping")
            twin = await client.post(base, json={"name": "Pedido", "keys": KEYS})
            assert twin.status_code == 409

            app.dependency_overrides[get_claims] = lambda: as_role(analyst, "analyst")
            assert [m["name"] for m in (await client.get(base)).json()] == ["Pedido"]
            denied = await client.patch(
                f"/api/v1/correlation-mappings/{mapping['id']}", json={"window_minutes": 5}
            )
            assert denied.status_code == 403

            app.dependency_overrides[get_claims] = lambda: as_role(admin, "admin")
            changed = await client.patch(
                f"/api/v1/correlation-mappings/{mapping['id']}", json={"window_minutes": 5}
            )
            assert changed.json()["window_minutes"] == 5
            removed = await client.delete(f"/api/v1/correlation-mappings/{mapping['id']}")
            assert removed.status_code == 204
            assert (await client.get(base)).json() == []
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("delete from doctor.tenants where id = :t"), {"t": tenant}
            )
            await connection.execute(
                text("delete from public.organizations where id = :t"), {"t": tenant}
            )
            await connection.execute(
                text("delete from auth.users where id = any(cast(:u as uuid[]))"),
                {"u": [admin, analyst]},
            )
