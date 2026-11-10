"""Jira pela API (#43): OAuth com state de uso único, tokens só no Vault, chamado uma vez."""

import json
import os
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aid_api.core.auth import Claims, get_claims
from aid_api.itsm.repo import ItsmRepository, get_itsm_repository
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


def atlassian(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/oauth/token":
        body = json.loads(request.content)
        if body["code"] != "codigo-bom":
            return httpx.Response(403, json={"error": "access_denied"})
        return httpx.Response(
            200, json={"access_token": "acesso", "refresh_token": "r1", "expires_in": 3600}
        )
    return httpx.Response(
        200, json=[{"id": "cloud-1", "name": "acme", "url": "https://acme.atlassian.net"}]
    )


@pytest.mark.asyncio
async def test_conecta_configura_e_abre_o_chamado_uma_vez(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    monkeypatch.setenv("AID_ATLASSIAN_CLIENT_ID", "app-doctor")
    monkeypatch.setenv("AID_ATLASSIAN_CLIENT_SECRET", "segredo-do-app")
    monkeypatch.setenv("AID_ATLASSIAN_REDIRECT_URI", "https://app.test/chamados/jira")
    tenant, admin, viewer, integration, incident = (str(uuid4()) for _ in range(5))
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values"
            " (:a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',"
            " :ea), (:v, '00000000-0000-0000-0000-000000000000', 'authenticated',"
            " 'authenticated', :ev)",
            "insert into public.organizations (id, name, slug) values (:t, 'Jira', :s)",
            "insert into doctor.tenants (id) values (:t)",
            "insert into public.organization_members (org_id, user_id, role)"
            " values (:t, :a, 'member'), (:t, :v, 'member')",
            "insert into doctor.memberships (tenant_id, user_id, role)"
            " values (:t, :a, 'admin'), (:t, :v, 'viewer')",
            "insert into doctor.integrations (id, tenant_id, name, source_system, target_system,"
            " environment) values (:i, :t, 'Pedidos', 'salesforce', 'sap', 'prd')",
            "insert into doctor.incidents (id, tenant_id, integration_id, title, category,"
            " severity, rule_code, rule_version, first_seen_at, last_seen_at) values (:x, :t, :i,"
            " 'Timeout', 'TIMEOUT', 'critical', 'INT-003', '2026.10.1', now(), now())",
        ):
            await connection.execute(
                text(sql),
                {
                    "t": tenant,
                    "a": admin,
                    "v": viewer,
                    "i": integration,
                    "x": incident,
                    "s": f"jira-{tenant[:8]}",
                    "ea": f"{admin}@a.test",
                    "ev": f"{viewer}@a.test",
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
    app.dependency_overrides[get_itsm_repository] = lambda: ItsmRepository(
        transport=httpx.MockTransport(atlassian)
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://api.test",
            headers={"authorization": "Bearer jwt"},
        ) as client:
            app.dependency_overrides[get_claims] = lambda: as_role(admin, "admin")
            assert (await client.get("/api/v1/itsm/jira")).json() is None
            started = (await client.post("/api/v1/itsm/jira/authorize")).json()["url"]
            query = parse_qs(urlparse(started).query)
            assert query["redirect_uri"] == ["https://app.test/chamados/jira"]
            assert "offline_access" in query["scope"][0]
            state = query["state"][0]
            denied = await client.post(
                "/api/v1/itsm/jira/callback", json={"code": "codigo-ruim", "state": state}
            )
            assert denied.status_code == 400
            connected = await client.post(
                "/api/v1/itsm/jira/callback", json={"code": "codigo-bom", "state": state}
            )
            assert connected.status_code == 200, connected.text
            assert connected.json()["sites"][0]["url"] == "https://acme.atlassian.net"
            assert "acesso" not in connected.text
            again = await client.post(
                "/api/v1/itsm/jira/callback", json={"code": "codigo-bom", "state": state}
            )
            assert (again.status_code, again.json()["code"]) == (400, "invalid_state")
            early = await client.post(f"/api/v1/incidents/{incident}/tickets")
            assert (early.status_code, early.json()["code"]) == (409, "jira_not_configured")
            configured = await client.put(
                "/api/v1/itsm/jira",
                json={"cloud_id": "cloud-1", "project_key": "SUST", "issue_type": "Incidente"},
            )
            assert configured.json()["status"] == "active"
            first = await client.post(f"/api/v1/incidents/{incident}/tickets")
            second = await client.post(f"/api/v1/incidents/{incident}/tickets")
            assert first.status_code == second.status_code == 202
            assert [t["status"] for t in second.json()] == ["creating"]

            # Canal Jira para Regras de alerta: sem configuração nem segredo.
            channel = await client.post(
                "/api/v1/notification-channels", json={"type": "jira", "name": "Chamado"}
            )
            assert (channel.status_code, channel.json()["config"]) == (201, {}), channel.text
            assert any(
                c["type"] == "jira"
                for c in (await client.get("/api/v1/notification-channels")).json()
            )

            app.dependency_overrides[get_claims] = lambda: as_role(viewer, "viewer")
            assert (await client.post(f"/api/v1/incidents/{incident}/tickets")).status_code == 403
            assert len((await client.get(f"/api/v1/incidents/{incident}/tickets")).json()) == 1

        async with engine.begin() as connection:
            # O token do endereço fica no Vault; a outbox não o leva.
            hook_token = await connection.scalar(
                text(
                    "select cast(doctor.get_itsm_tokens(id) as jsonb) ->> 'hook_token'"
                    " from doctor.itsm_connections where tenant_id = cast(:t as uuid)"
                ),
                {"t": tenant},
            )
            leaked = await connection.scalar(
                text(
                    "select count(*) from doctor.outbox_messages where tenant_id = cast(:t as uuid)"
                    " and payload::text like '%' || cast(:h as text) || '%'"
                ),
                {"t": tenant, "h": hook_token},
            )
            assert hook_token
            assert leaked == 0
            tickets = await connection.scalar(
                text(
                    "select count(*) from doctor.outbox_messages where topic = 'itsm.ticket'"
                    " and tenant_id = cast(:t as uuid)"
                ),
                {"t": tenant},
            )
        assert tickets == 1
        anonymous = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=anonymous), base_url="http://api.test"
        ) as client:
            wrong = await client.post("/api/v1/itsm/jira/hooks/" + "x" * 40, json={"forjado": 1})
            right = await client.post(f"/api/v1/itsm/jira/hooks/{hook_token}", json={})
            # A rajada do mesmo evento vira uma leitura só; outra issue pede a dela.
            again = await client.post(f"/api/v1/itsm/jira/hooks/{hook_token}", json={})
            issue = await client.post(
                f"/api/v1/itsm/jira/hooks/{hook_token}", json={"issue": {"key": "SUST-881"}}
            )
            assert wrong.status_code == right.status_code == again.status_code == 204
            assert issue.status_code == 204
        async with engine.begin() as connection:
            syncs = [
                row[0]
                for row in await connection.execute(
                    text(
                        "select payload ->> 'issue_key' from doctor.outbox_messages"
                        " where topic = 'itsm.sync' and tenant_id = cast(:t as uuid) order by id"
                    ),
                    {"t": tenant},
                )
            ]
        # A configuração, o evento sem issue e o da SUST-881.
        assert syncs == [None, None, "SUST-881"]
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
                {"u": [admin, viewer]},
            )
