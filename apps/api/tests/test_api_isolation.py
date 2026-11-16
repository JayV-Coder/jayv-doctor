"""Isolamento fora do banco (ticket #27): para cada rota com recurso no caminho, o Owner (com MFA)
da Organização A pede o recurso da Organização B e recebe 404, sem revelar que ele existe. Rota
nova com parâmetro precisa entrar em ROUTES, ou o teste falha. Roda com INTEGRATION_DB_URL."""

import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aid_api.core.auth import Claims, get_claims
from aid_api.core.storage import Storage, get_storage
from aid_api.main import create_app
from aid_api.orgs.mailer import Mailer, get_mailer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
# O inventário das rotas roda sempre; só a chamada contra o banco precisa do Postgres.
needs_db = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")

# Ids de B no corpo: a operação não pode ligar nada de A a B nem mudar B.
BODY_CASES: list[tuple[str, str, dict[str, Any]]] = [
    (
        "POST",
        "/api/v1/imports",
        {
            "integration_id": "{integration}",
            "filename": "x.ndjson",
            "size_bytes": 10,
            "sha256": "f" * 64,
        },
    ),
    ("POST", "/api/v1/ingestion-tokens", {"name": "Token", "integration_id": "{integration}"}),
    ("PATCH", "/api/v1/incidents/{own_incident}", {"assignee_id": "{user_b}"}),
    (
        "POST",
        "/api/v1/alert-rules",
        {
            "name": "Invasora",
            "conditions": {"type": "connector_failing"},
            "channels": ["{channel}"],
        },
    ),
    (
        "POST",
        "/api/v1/integrations/{own_integration}/correlation-mappings",
        {
            "name": "Pedido",
            "keys": [{"system": "sap", "field": "execution_id"}],
            "lookup": {"connector_id": "{connector}", "entity": "Order", "field": "OrderNumber"},
        },
    ),
]

# (método, caminho, recurso de B no parâmetro, corpo)
ROUTES: list[tuple[str, str, str, dict[str, Any] | None]] = [
    ("POST", "/api/v1/orgs/{tenant_id}/switch", "tenant", None),
    ("PATCH", "/api/v1/memberships/{target}", "membership", {"role": "viewer"}),
    ("DELETE", "/api/v1/memberships/{target}", "membership", None),
    ("POST", "/api/v1/invitations/{target}/resend", "invitation", None),
    ("DELETE", "/api/v1/invitations/{target}", "invitation", None),
    ("PATCH", "/api/v1/integrations/{target}", "integration", {"name": "Invadida"}),
    ("POST", "/api/v1/integrations/{target}/archive", "integration", None),
    ("PATCH", "/api/v1/alert-rules/{target}", "alert_rule", {"enabled": False}),
    ("DELETE", "/api/v1/alert-rules/{target}", "alert_rule", None),
    ("DELETE", "/api/v1/notification-channels/{target}", "channel", None),
    ("DELETE", "/api/v1/push-subscriptions/{target}", "push", None),
    ("PATCH", "/api/v1/webhooks/{target}", "webhook", {"enabled": False}),
    ("GET", "/api/v1/incidents/{target}/tickets", "incident", None),
    ("POST", "/api/v1/incidents/{target}/tickets", "incident", None),
    ("POST", "/api/v1/webhooks/{target}/rotate-secret", "webhook", None),
    ("DELETE", "/api/v1/webhooks/{target}", "webhook", None),
    ("GET", "/api/v1/webhooks/{target}/deliveries", "webhook", None),
    ("POST", "/api/v1/webhook-deliveries/{target}/resend", "webhook_delivery", None),
    ("POST", "/api/v1/sso/domains/{target}/verify", "sso_domain", None),
    ("DELETE", "/api/v1/sso/domains/{target}", "sso_domain", None),
    ("GET", "/api/v1/integrations/{target}/correlation-mappings", "integration", None),
    (
        "POST",
        "/api/v1/integrations/{target}/correlation-mappings",
        "integration",
        {"name": "Invasor", "keys": [{"system": "sap", "field": "execution_id"}]},
    ),
    ("PATCH", "/api/v1/correlation-mappings/{target}", "mapping", {"name": "Invadido"}),
    ("DELETE", "/api/v1/correlation-mappings/{target}", "mapping", None),
    ("POST", "/api/v1/imports/{target}/upload-url", "import", None),
    ("POST", "/api/v1/imports/{target}/complete", "import", None),
    ("POST", "/api/v1/ingestion-tokens/{target}/revoke", "token", None),
    ("GET", "/api/v1/connectors/{target}", "connector", None),
    ("PATCH", "/api/v1/connectors/{target}", "connector", {"name": "Invadido"}),
    ("POST", "/api/v1/connectors/{target}/test", "connector", {"credential": "{}"}),
    ("POST", "/api/v1/connectors/{target}/sync", "connector", None),
    ("POST", "/api/v1/connectors/{target}/pause", "connector", None),
    ("POST", "/api/v1/connectors/{target}/resume", "connector", None),
    ("GET", "/api/v1/connectors/{target}/syncs", "connector", None),
    ("GET", "/api/v1/executions/{target}", "execution", None),
    ("GET", "/api/v1/events/{target}", "event", None),
    ("GET", "/api/v1/raw-logs/{target}/download", "raw_log", None),
    ("GET", "/api/v1/incidents/{target}", "incident", None),
    ("PATCH", "/api/v1/incidents/{target}", "incident", {"status": "investigating"}),
    ("GET", "/api/v1/incidents/{target}/comments", "incident", None),
    ("POST", "/api/v1/incidents/{target}/comments", "incident", {"body_md": "Oi", "mentions": []}),
    ("POST", "/api/v1/knowledge/documents/{target}/finish", "document", None),
    ("DELETE", "/api/v1/knowledge/documents/{target}", "document", None),
    ("POST", "/api/v1/incidents/{incident}/diagnoses", "incident", {}),
    ("GET", "/api/v1/incidents/{incident}/diagnoses", "incident", None),
    ("GET", "/api/v1/diagnoses/{target}", "diagnosis", None),
    ("POST", "/api/v1/diagnoses/{target}/feedback", "diagnosis", {"verdict": "accepted"}),
    ("POST", "/api/v1/incidents/{incident}/knowledge", "incident", None),
    ("POST", "/api/v1/incidents/{incident}/reports", "incident", {"format": "md"}),
    ("GET", "/api/v1/incidents/{incident}/reports", "incident", None),
    ("GET", "/api/v1/reports/{target}", "report", None),
    ("POST", "/api/v1/reports/{target}/shares", "report", None),
    ("DELETE", "/api/v1/reports/{target}/shares/{share}", "report", None),
    ("PATCH", "/api/v1/agents/{target}", "agent", {"config": {"collections": []}}),
    ("POST", "/api/v1/agents/{target}/revoke", "agent", None),
    ("POST", "/api/v1/agents/{target}/rotate", "agent", None),
]


def test_toda_rota_com_recurso_no_caminho_esta_na_suite() -> None:
    paths = create_app().openapi()["paths"]
    declared = {
        (method.upper(), path)
        for path, operations in paths.items()
        if "{" in path
        for method in operations
    }
    assert declared == {(method, path) for method, path, _, _ in ROUTES}


class Untouched(Storage, Mailer):
    """Storage e e-mail que nunca podem ser alcançados com recurso de outra Organização."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def sign_upload(self, token: str, path: str, bucket: str = "x") -> str:
        self.calls.append(f"upload {path}")
        return "https://storage.test"

    async def sign_download(
        self, token: str, path: str, seconds: int, bucket: str = "doctor-raw-logs"
    ) -> str:
        self.calls.append(f"download {path}")
        return "https://storage.test"

    async def delete(self, token: str, path: str, bucket: str) -> None:
        self.calls.append(f"delete {path}")

    async def head(self, token: str, path: str, limit: int) -> None:
        self.calls.append(f"head {path}")

    def send_invitation(self, email: str, organization: str, url: str) -> None:
        self.calls.append(f"mail {email}")


# Repetida de test_api_integration.py: um conftest.py aqui colidiria, no mypy, com o do worker de
# diagnóstico (os nomes de módulo de teste são únicos no repositório).
@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


async def seed(engine: AsyncEngine) -> dict[str, str]:
    ids = {
        name: str(uuid4())
        for name in (
            "a",
            "tenant",
            "user_a",
            "user_b",
            "membership",
            "invitation",
            "integration",
            "import",
            "raw_log",
            "token",
            "connector",
            "execution",
            "event",
            "incident",
            "diagnosis",
            "report",
            "share",
            "agent",
            "alert_rule",
            "channel",
            "push",
            "webhook",
            "webhook_delivery",
            "sso_domain",
            "mapping",
            "document",
            "own_integration",
            "own_incident",
        )
    }
    statements = [
        "insert into auth.users (id, instance_id, aud, role, email) values"
        " (:user_a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',"
        " :email_a), (:user_b, '00000000-0000-0000-0000-000000000000', 'authenticated',"
        " 'authenticated', :email_b)",
        "insert into public.organizations (id, name, slug) values (:a, 'A', :slug_a),"
        " (:tenant, 'B', :slug_b)",
        "insert into doctor.tenants (id) values (:a), (:tenant)",
        "insert into public.organization_members (org_id, user_id, role)"
        " values (:a, :user_a, 'member'), (:tenant, :user_b, 'member')",
        "insert into doctor.memberships (tenant_id, user_id, role) values (:a, :user_a, 'owner')",
        "insert into doctor.memberships (id, tenant_id, user_id, role)"
        " values (:membership, :tenant, :user_b, 'owner')",
        "insert into doctor.invitations (id, tenant_id, email, role, token_hash, invited_by)"
        " values (:invitation, :tenant, 'novo@b.test', 'viewer', repeat('e', 64), :user_b)",
        "insert into doctor.integrations (id, tenant_id, name, source_system, target_system,"
        " environment) values (:integration, :tenant, 'Notas', 'sap', 'gcp', 'prd'),"
        " (:own_integration, :a, 'Pedidos', 'salesforce', 'sap', 'prd')",
        "insert into doctor.incidents (id, tenant_id, integration_id, title, category, severity,"
        " rule_code, rule_version, first_seen_at, last_seen_at, execution_count) values"
        " (:own_incident, :a, :own_integration, 'Timeout A', 'TIMEOUT', 'high', 'INT-003',"
        " '2026.10.1', now(), now(), 1)",
        "insert into doctor.raw_log_objects (id, tenant_id, storage_path, sha256, size_bytes,"
        " source) values (:raw_log, :tenant, :path, repeat('a', 64), 10, 'api')",
        "insert into doctor.imports (id, tenant_id, integration_id, filename, size_bytes, sha256)"
        " values (:import, :tenant, :integration, 'logs.ndjson', 10, repeat('b', 64))",
        "insert into doctor.ingestion_tokens (id, tenant_id, name, integration_id, token_hash,"
        " prefix) values (:token, :tenant, 'Token', :integration, repeat('c', 64), 'aid_test')",
        "insert into doctor.connectors (id, tenant_id, integration_id, provider, name)"
        " values (:connector, :tenant, :integration, 'gcp', 'Cloud Logging')",
        "select doctor.ensure_event_partition('2026-11-02')",
        "insert into doctor.executions (id, tenant_id, integration_id, first_event_at,"
        " last_event_at) values (:execution, :tenant, :integration, '2026-11-02T14:00:00Z',"
        " '2026-11-02T14:00:30Z')",
        "insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version,"
        " source, operation, severity, dedup_key, execution_ref, raw_log_object_id) values"
        " (:event, :tenant, :integration, '2026-11-02T14:00:10Z', '1.0', '{}', 'BAPI', 'ERROR',"
        " 'dedup-isolamento', :execution, :raw_log)",
        "insert into doctor.incidents (id, tenant_id, integration_id, title, category, severity,"
        " rule_code, rule_version, first_seen_at, last_seen_at, execution_count, status,"
        " resolved_at, resolution_note) values (:incident, :tenant, :integration, 'Timeout',"
        " 'TIMEOUT', 'high', 'INT-003', '2026.10.1', now(), now(), 1, 'resolved', now(),"
        " 'Gateway ajustado.')",
        "insert into doctor.diagnoses (id, tenant_id, incident_id, version, status, stage,"
        " requested_mode, mode, processing_key, published_at) values (:diagnosis, :tenant,"
        " :incident, 1, 'published', 'done', 'hybrid', 'hybrid', 'k', now())",
        "insert into doctor.diagnosis_feedback (tenant_id, diagnosis_id, reviewer_id, verdict)"
        " values (:tenant, :diagnosis, :user_b, 'accepted')",
        "insert into doctor.notification_channels (id, tenant_id, type, name, config)"
        " values (:channel, :tenant, 'email', 'Gestores', '{}')",
        "insert into doctor.alert_rules (id, tenant_id, name, conditions, channels)"
        " values (:alert_rule, :tenant, 'Falhas', '{\"type\": \"connector_failing\"}', '[]')",
        "insert into doctor.push_subscriptions (id, tenant_id, user_id, endpoint, p256dh, auth)"
        " values (:push, :tenant, :user_b, 'https://fcm.googleapis.com/fcm/send/b',"
        " repeat('p', 87), repeat('a', 22))",
        "insert into doctor.webhooks (id, tenant_id, name, url, events, secret_id)"
        " values (:webhook, :tenant, 'ITSM', 'https://itsm.varejo.test/aid',"
        " array['incident.opened'], gen_random_uuid())",
        "insert into doctor.webhook_deliveries (id, tenant_id, webhook_id, event, subject)"
        " values (:webhook_delivery, :tenant, :webhook, 'incident.opened', '{}')",
        "insert into doctor.sso_domains (id, tenant_id, domain)"
        " values (:sso_domain, :tenant, :sso_domain_name)",
        "insert into doctor.correlation_mappings (id, tenant_id, integration_id, name, keys)"
        " values (:mapping, :tenant, :integration, 'Pedido',"
        ' \'[{"system": "sap", "field": "execution_id"}]\')',
        "insert into doctor.agents (id, tenant_id, integration_id, name, registration_token_hash,"
        " registration_expires_at) values (:agent, :tenant, :integration, 'Agente',"
        " repeat('a', 64), now() + interval '1 day')",
        "insert into doctor.reports (id, tenant_id, incident_id, diagnosis_id, format, status,"
        " storage_path, content_sha256, processing_key) values (:report, :tenant, :incident,"
        " :diagnosis, 'pdf', 'ready', :report_path, repeat('c', 64), 'r')",
        "insert into doctor.report_shares (id, tenant_id, report_id, token_hash, download_url,"
        " expires_at) values (:share, :tenant, :report, repeat('d', 64), 'https://s.test/r',"
        " now() + interval '1 day')",
        "insert into doctor.knowledge_documents (id, tenant_id, title, source, storage_path,"
        " content_type, size_bytes) values (:document, :tenant, 'Runbook', 'upload', :doc_path,"
        " 'text/markdown', 10)",
    ]
    params = {
        **ids,
        "email_a": f"{ids['user_a']}@a.test",
        "email_b": f"{ids['user_b']}@b.test",
        "slug_a": f"a-{ids['a'][:30]}",
        "slug_b": f"b-{ids['tenant'][:30]}",
        "path": f"{ids['tenant']}/api/lote.json",
        "doc_path": f"{ids['tenant']}/{ids['document']}/document.md",
        "report_path": f"{ids['tenant']}/{ids['report']}.pdf",
        "sso_domain_name": f"b-{ids['tenant'][:8]}.test",
    }
    async with engine.begin() as connection:
        for sql in statements:
            await connection.execute(text(sql), params)
    return ids


async def drop(engine: AsyncEngine, ids: dict[str, str]) -> None:
    # Toda tabela de tenant referencia doctor.tenants com on delete cascade.
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from doctor.tenants where id in (:a, :b)"),
            {"a": ids["a"], "b": ids["tenant"]},
        )
        await connection.execute(
            text("delete from public.organizations where id in (:a, :b)"),
            {"a": ids["a"], "b": ids["tenant"]},
        )
        await connection.execute(
            text("delete from auth.users where id in (:a, :b)"),
            {"a": ids["user_a"], "b": ids["user_b"]},
        )


async def snapshot(engine: AsyncEngine, tenant: str) -> dict[str, str]:
    """Hash do conteúdo de cada tabela de tenant da Organização: qualquer escrita muda o hash."""
    async with engine.begin() as connection:
        tables = (
            await connection.execute(
                text(
                    "select c.relname from pg_class c where c.relnamespace = 'doctor'::regnamespace"
                    " and c.relkind in ('r', 'p') and not c.relispartition and exists (select 1"
                    " from pg_attribute a where a.attrelid = c.oid and a.attname = 'tenant_id')"
                    " order by 1"
                )
            )
        ).scalars()
        found = {}
        for table in list(tables):
            found[table] = await connection.scalar(
                text(
                    f"select md5(coalesce(string_agg(to_jsonb(t)::text, '|'"  # noqa: S608
                    f" order by to_jsonb(t)::text), '')) from doctor.{table} t"
                    " where tenant_id = cast(:t as uuid)"
                ),
                {"t": tenant},
            )
        return found


@needs_db
@pytest.mark.asyncio
async def test_recurso_de_outra_organizacao_responde_404(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_api.core.db as db

    ids = await seed(engine)
    try:
        monkeypatch.setattr(db, "get_engine", lambda: engine)
        raw = {
            "sub": ids["user_a"],
            "role": "authenticated",
            "aal": "aal2",
            "tenant_id": ids["a"],
            "tenant_role": "owner",
        }
        claims = Claims(
            sub=ids["user_a"],
            email=None,
            aal="aal2",
            tenant_id=ids["a"],
            tenant_role="owner",
            raw=raw,
        )
        app = create_app()
        app.dependency_overrides[get_claims] = lambda: claims
        untouched = Untouched()
        app.dependency_overrides[get_storage] = lambda: untouched
        app.dependency_overrides[get_mailer] = lambda: untouched
        transport = httpx.ASGITransport(app=app)
        before = await snapshot(engine, ids["tenant"])
        outcomes: dict[str, int] = {}
        leaks: dict[str, tuple[Any, Any]] = {}
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://api.test",
            headers={"authorization": "Bearer jwt"},
        ) as client:
            # Controle positivo: com o recurso da própria Organização, a mesma montagem responde.
            own = await client.get(f"/api/v1/incidents/{ids['own_incident']}")
            assert own.status_code == 200, own.text

            for method, path, resource, body in ROUTES:

                def url(value: str, template: str = path) -> str:
                    return (
                        template.replace("{target}", value)
                        .replace("{incident}", value)
                        .replace("{tenant_id}", value)
                        .replace("{share}", ids["share"])
                    )

                response = await client.request(method, url(ids[resource]), json=body)
                outcomes[f"{method} {path}"] = response.status_code
                # Igual à resposta para um id que não existe: nada revela que o de B existe.
                unknown = await client.request(method, url(str(uuid4())), json=body)
                answer = (response.status_code, response.json().get("code"))
                baseline = (unknown.status_code, unknown.json().get("code"))
                if answer != baseline:
                    leaks[f"{method} {path}"] = (answer, baseline)

            def fill(value: Any) -> Any:
                if isinstance(value, dict):
                    return {key: fill(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [fill(item) for item in value]
                if isinstance(value, str) and value.startswith("{"):
                    return ids[value[1:-1]]
                return value

            for method, path, payload in BODY_CASES:
                target = path.replace("{own_incident}", ids["own_incident"]).replace(
                    "{own_integration}", ids["own_integration"]
                )
                response = await client.request(method, target, json=fill(payload))
                outcomes[f"{method} {path} (id de B no corpo)"] = response.status_code
        assert {
            route: status for route, status in outcomes.items() if status not in (404, 422)
        } == {}
        assert {r: s for r, s in outcomes.items() if "corpo" not in r and s != 404} == {}
        assert leaks == {}
        assert untouched.calls == []
        # Nada de B mudou, em nenhuma tabela (inclusive outbox e auditoria).
        assert await snapshot(engine, ids["tenant"]) == before
        async with engine.begin() as connection:
            assignee = await connection.scalar(
                text("select assignee_id from doctor.incidents where id = :i"),
                {"i": ids["own_incident"]},
            )
        assert assignee is None
    finally:
        await drop(engine, ids)
