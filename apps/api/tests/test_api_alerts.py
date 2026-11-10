"""Alertas pela API (#41): Regras e canais só para gestores, webhook só no Vault, push só nos
serviços dos navegadores e cada Usuário com os próprios aparelhos."""

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
WEBHOOK = "https://hooks.slack.com/services/T0/B0/segredo-do-canal"
PUSH = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/aparelho-1",
    "keys": {"p256dh": "B" * 87, "auth": "a" * 22},
}


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


@pytest.mark.asyncio
async def test_gestor_configura_e_analyst_cuida_so_do_proprio_push(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    monkeypatch.setenv("AID_VAPID_PUBLIC_KEY", "BPublicaDeTeste")
    tenant, admin, analyst = (str(uuid4()) for _ in range(3))
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values"
            " (:a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',"
            " :ea), (:n, '00000000-0000-0000-0000-000000000000', 'authenticated',"
            " 'authenticated', :en)",
            "insert into public.organizations (id, name, slug) values (:t, 'Alertas', :s)",
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
                    "s": f"alertas-{tenant[:8]}",
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
            bad = await client.post(
                "/api/v1/notification-channels",
                json={"type": "slack", "name": "Errado", "webhook_url": "https://evil.test/x"},
            )
            assert (bad.status_code, bad.json()["code"]) == (422, "invalid_alert")
            slack = await client.post(
                "/api/v1/notification-channels",
                json={"type": "slack", "name": "Plantão", "webhook_url": WEBHOOK},
            )
            assert slack.status_code == 201, slack.text
            assert "segredo-do-canal" not in slack.text
            listed = await client.get("/api/v1/notification-channels")
            assert "segredo-do-canal" not in listed.text
            rule = await client.post(
                "/api/v1/alert-rules",
                json={
                    "name": "Crítico em prd",
                    "conditions": {
                        "type": "incident",
                        "min_severity": "critical",
                        "environments": ["prd"],
                    },
                    "channels": [slack.json()["id"]],
                    "quiet_hours": {"start": "22:00", "end": "07:00"},
                },
            )
            assert rule.status_code == 201, rule.text
            assert rule.json()["quiet_hours"]["timezone"] == "America/Sao_Paulo"
            wrong = await client.post(
                "/api/v1/alert-rules",
                json={"name": "Ruim", "conditions": {"type": "incident", "min_severity": "x"}},
            )
            assert wrong.status_code == 422
            off = await client.patch(
                f"/api/v1/alert-rules/{rule.json()['id']}", json={"enabled": False}
            )
            assert off.json()["enabled"] is False

            app.dependency_overrides[get_claims] = lambda: as_role(analyst, "analyst")
            assert (await client.get("/api/v1/alert-rules")).json()[0]["name"] == "Crítico em prd"
            denied = await client.patch(
                f"/api/v1/alert-rules/{rule.json()['id']}", json={"enabled": True}
            )
            assert denied.status_code == 403
            assert (await client.get("/api/v1/push/key")).json() == {
                "public_key": "BPublicaDeTeste"
            }
            internal = await client.post(
                "/api/v1/push-subscriptions",
                json={**PUSH, "endpoint": "https://metadata.google.internal/push"},
            )
            assert internal.status_code == 422
            mine = await client.post("/api/v1/push-subscriptions", json=PUSH)
            assert mine.status_code == 201, mine.text
            again = await client.post("/api/v1/push-subscriptions", json=PUSH)
            assert again.status_code == 201
            assert len((await client.get("/api/v1/push-subscriptions")).json()) == 1
            saved = await client.put(
                "/api/v1/alert-preferences",
                json={"quiet_hours": {"start": "23:00", "end": "06:00"}},
            )
            assert saved.json()["quiet_hours"]["start"] == "23:00"

            app.dependency_overrides[get_claims] = lambda: as_role(admin, "admin")
            assert (await client.get("/api/v1/push-subscriptions")).json() == []
            assert (await client.get("/api/v1/alert-preferences")).json() == {"quiet_hours": None}
            removed = await client.delete(f"/api/v1/notification-channels/{slack.json()['id']}")
            assert removed.status_code == 204
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
