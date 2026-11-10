"""ServiceNow pela API (#44): credenciais no Vault, regra de grupos, webhook da Business Rule."""

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
CONFIG = {
    "instance_url": "https://acme.service-now.com",
    "client_id": "app-doctor",
    "client_secret": "segredo-da-instancia",
    "assignment_groups": {"sap": "SAP Basis"},
    "default_group": "Service Desk",
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
async def test_configura_abre_o_incident_e_recebe_a_business_rule(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    monkeypatch.setenv("AID_PUBLIC_API_URL", "https://api.test")
    tenant, admin, viewer, integration, incident = (str(uuid4()) for _ in range(5))
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values"
            " (:a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',"
            " :ea), (:v, '00000000-0000-0000-0000-000000000000', 'authenticated',"
            " 'authenticated', :ev)",
            "insert into public.organizations (id, name, slug) values (:t, 'SN', :s)",
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
                    "s": f"sn-{tenant[:8]}",
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
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://api.test",
            headers={"authorization": "Bearer jwt"},
        ) as client:
            app.dependency_overrides[get_claims] = lambda: as_role(admin, "admin")
            assert (await client.get("/api/v1/itsm/servicenow")).json() is None
            internal = await client.put(
                "/api/v1/itsm/servicenow", json={**CONFIG, "instance_url": "https://10.0.0.1"}
            )
            assert internal.status_code == 422
            first = await client.put("/api/v1/itsm/servicenow", json=CONFIG)
            assert first.status_code == 200, first.text
            hook_url = first.json()["hook_url"]
            assert hook_url.startswith("https://api.test/api/v1/itsm/servicenow/hooks/")
            assert "segredo-da-instancia" not in first.text
            # Mudar a regra não pede o secret nem troca o endereço da Business Rule.
            groups = await client.put(
                "/api/v1/itsm/servicenow",
                json={
                    **{k: v for k, v in CONFIG.items() if k != "client_secret"},
                    "assignment_groups": {"sap": "SAP N2", "gcp": "Cloud"},
                },
            )
            assert groups.status_code == 200, groups.text
            assert groups.json()["hook_url"] is None
            assert groups.json()["connection"]["assignment_groups"] == {
                "sap": "SAP N2",
                "gcp": "Cloud",
            }
            moved = await client.put(
                "/api/v1/itsm/servicenow",
                json={
                    **{k: v for k, v in CONFIG.items() if k != "client_secret"},
                    "instance_url": "https://outra.service-now.com",
                },
            )
            assert (moved.status_code, moved.json()["code"]) == (422, "secret_required")
            # Repetição idempotente de quem não gerou endereço: nulo, não a máscara do segredo.
            replay_body = {k: v for k, v in CONFIG.items() if k != "client_secret"}
            headers = {"Idempotency-Key": "servicenow-grupos-1"}
            once = await client.put("/api/v1/itsm/servicenow", json=replay_body, headers=headers)
            twice = await client.put("/api/v1/itsm/servicenow", json=replay_body, headers=headers)
            assert once.json()["hook_url"] is None
            assert twice.json()["hook_url"] is None
            # Sem Jira: a mensagem fala do ITSM, não do Jira.
            no_jira = await client.post(f"/api/v1/incidents/{incident}/tickets?provider=jira")
            assert (no_jira.status_code, no_jira.json()["code"]) == (409, "itsm_not_configured")
            opened = await client.post(f"/api/v1/incidents/{incident}/tickets?provider=servicenow")
            assert opened.status_code == 202, opened.text
            assert [(t["provider"], t["status"]) for t in opened.json()] == [
                ("servicenow", "creating")
            ]

            # Instância nova: secret e endereço novos; o chamado da antiga pode ser aberto de novo.
            moved_ok = await client.put(
                "/api/v1/itsm/servicenow",
                json={**CONFIG, "instance_url": "https://nova.service-now.com"},
            )
            assert moved_ok.status_code == 200, moved_ok.text
            new_hook = moved_ok.json()["hook_url"]
            assert new_hook
            assert new_hook != hook_url
            listed = (await client.get(f"/api/v1/incidents/{incident}/tickets")).json()
            assert [t["status"] for t in listed] == ["failed"]

            app.dependency_overrides[get_claims] = lambda: as_role(viewer, "viewer")
            assert (await client.put("/api/v1/itsm/servicenow", json=CONFIG)).status_code == 403
            assert (await client.get("/api/v1/itsm/servicenow")).json()["default_group"] == (
                "Service Desk"
            )

        anonymous = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=anonymous), base_url="http://api.test"
        ) as client:
            old = hook_url.removeprefix("https://api.test")
            path = new_hook.removeprefix("https://api.test")
            wrong = await client.post(
                "/api/v1/itsm/servicenow/hooks/" + "x" * 40, json={"number": "INC0010001"}
            )
            stale = await client.post(old, json={"number": "INC0010002"})
            right = await client.post(path, json={"number": "INC0010001"})
            assert wrong.status_code == stale.status_code == right.status_code == 204
        async with engine.begin() as connection:
            syncs = [
                row[0]
                for row in await connection.execute(
                    text(
                        "select payload from doctor.outbox_messages where topic = 'itsm.sync'"
                        " and tenant_id = cast(:t as uuid) order by id"
                    ),
                    {"t": tenant},
                )
            ]
        # Só o endereço atual pede leitura (o da instância antiga, não).
        keys = [s.get("issue_key") for s in syncs if s.get("issue_key")]
        assert keys == ["INC0010001"]
        assert all(s.get("provider") == "servicenow" for s in syncs)
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
