"""Webhooks pela API (#42): só gestor, endereço seguro, segredo mostrado uma vez."""

import os
from collections.abc import AsyncIterator, Sequence
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


@pytest.mark.asyncio
async def test_cadastro_recusa_metadados_e_segredo_aparece_uma_vez(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_alerts import network
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)

    async def public(_: str) -> Sequence[str]:
        return ["200.160.2.3"]

    # Sem DNS no teste: o nome do ITSM resolve para um IP público.
    monkeypatch.setattr(network, "resolve", public)
    monkeypatch.setattr(network.check_url, "__defaults__", (public,))
    tenant, admin, analyst = (str(uuid4()) for _ in range(3))
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values"
            " (:a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',"
            " :ea), (:n, '00000000-0000-0000-0000-000000000000', 'authenticated',"
            " 'authenticated', :en)",
            "insert into public.organizations (id, name, slug) values (:t, 'Hooks', :s)",
            "insert into doctor.tenants (id) values (:t)",
            "insert into public.organization_members (org_id, user_id, role)"
            " values (:t, :a, 'member'), (:t, :n, 'member')",
            "insert into doctor.memberships (tenant_id, user_id, role)"
            " values (:t, :a, 'admin'), (:t, :n, 'analyst')",
        ):
            await connection.execute(
                text(sql),
                {
                    "t": tenant,
                    "a": admin,
                    "n": analyst,
                    "s": f"hooks-{tenant[:8]}",
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
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://api.test",
            headers={"authorization": "Bearer jwt"},
        ) as client:
            app.dependency_overrides[get_claims] = lambda: as_role(admin, "admin")
            for unsafe in (
                "http://169.254.169.254",
                "https://169.254.169.254/latest/meta-data",
                "https://10.0.0.5/hook",
                "https://metadata.google.internal/x",
            ):
                refused = await client.post(
                    "/api/v1/webhooks",
                    json={"name": "Ruim", "url": unsafe, "events": ["incident.opened"]},
                )
                assert (refused.status_code, refused.json()["code"]) == (422, "unsafe_url"), unsafe
            body = {
                "name": "ITSM",
                "url": "https://itsm.acme.com.br/aid",
                "events": ["incident.opened", "incident.resolved"],
            }
            created = await client.post(
                "/api/v1/webhooks", json=body, headers={"Idempotency-Key": "criar-itsm"}
            )
            assert created.status_code == 201, created.text
            secret = created.json()["secret"]
            assert secret.startswith("whsec_")
            # A repetição devolve a máscara: o segredo não fica guardado na idempotência.
            replay = await client.post(
                "/api/v1/webhooks", json=body, headers={"Idempotency-Key": "criar-itsm"}
            )
            assert (replay.json()["id"], replay.json()["secret"]) == (
                created.json()["id"],
                "[exibido uma vez]",
            )
            async with engine.begin() as connection:
                stored = await connection.scalar(
                    text(
                        "select count(*) from doctor.idempotency_keys"
                        " where response_body like '%whsec_%'"
                    )
                )
            assert stored == 0
            listed = await client.get("/api/v1/webhooks")
            assert secret not in listed.text
            assert listed.json()[0]["events"] == ["incident.opened", "incident.resolved"]
            rotated = await client.post(f"/api/v1/webhooks/{created.json()['id']}/rotate-secret")
            assert rotated.json()["secret"] not in (secret, None)
            off = await client.patch(
                f"/api/v1/webhooks/{created.json()['id']}", json={"enabled": False}
            )
            assert off.json()["enabled"] is False
            assert (
                await client.get(f"/api/v1/webhooks/{created.json()['id']}/deliveries")
            ).json() == []

            app.dependency_overrides[get_claims] = lambda: as_role(analyst, "analyst")
            assert (await client.get("/api/v1/webhooks")).status_code == 403
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
