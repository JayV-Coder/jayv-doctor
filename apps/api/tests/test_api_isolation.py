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
from aid_api.core.idempotency import IdempotencyStore, get_idempotency_store
from aid_api.core.storage import Storage, get_storage
from aid_api.main import create_app
from aid_api.orgs.mailer import Mailer, get_mailer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")

# (método, caminho, recurso de B no parâmetro, corpo)
ROUTES: list[tuple[str, str, str, dict[str, Any] | None]] = [
    ("POST", "/api/v1/orgs/{tenant_id}/switch", "tenant", None),
    ("PATCH", "/api/v1/memberships/{target}", "membership", {"role": "viewer"}),
    ("DELETE", "/api/v1/memberships/{target}", "membership", None),
    ("POST", "/api/v1/invitations/{target}/resend", "invitation", None),
    ("DELETE", "/api/v1/invitations/{target}", "invitation", None),
    ("PATCH", "/api/v1/integrations/{target}", "integration", {"name": "Invadida"}),
    ("POST", "/api/v1/integrations/{target}/archive", "integration", None),
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


class NoReplay(IdempotencyStore):
    """Sem gravar respostas: cada chamada chega à rota (o replay tem teste próprio)."""

    def __init__(self) -> None:
        pass


class Untouched(Storage, Mailer):
    """Storage e e-mail que nunca podem ser alcançados com recurso de outra Organização."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def sign_upload(self, token: str, path: str, bucket: str = "x") -> str:
        self.calls.append(f"upload {path}")
        return "https://storage.test"

    async def sign_download(self, token: str, path: str, seconds: int) -> str:
        self.calls.append(f"download {path}")
        return "https://storage.test"

    async def delete(self, token: str, path: str, bucket: str) -> None:
        self.calls.append(f"delete {path}")

    def send_invitation(self, email: str, organization: str, url: str) -> None:
        self.calls.append(f"mail {email}")


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
            "document",
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
        " environment) values (:integration, :tenant, 'Notas', 'sap', 'gcp', 'prd')",
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
    }
    async with engine.begin() as connection:
        for sql in statements:
            await connection.execute(text(sql), params)
    return ids


async def drop(engine: AsyncEngine, ids: dict[str, str]) -> None:
    async with engine.begin() as connection:
        for tenant in (ids["a"], ids["tenant"]):
            for table in (
                "diagnoses",
                "incidents",
                "events",
                "executions",
                "imports",
                "ingestion_tokens",
                "connectors",
                "raw_log_objects",
                "knowledge_documents",
                "integrations",
                "invitations",
                "audit_logs",
                "outbox_messages",
            ):
                await connection.execute(
                    text(f"delete from doctor.{table} where tenant_id = cast(:t as uuid)"),  # noqa: S608
                    {"t": tenant},
                )
            await connection.execute(
                text("delete from doctor.tenants where id = :t"), {"t": tenant}
            )
            await connection.execute(
                text("delete from public.organizations where id = :t"), {"t": tenant}
            )
        await connection.execute(
            text("delete from auth.users where id in (:a, :b)"),
            {"a": ids["user_a"], "b": ids["user_b"]},
        )


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
        app.dependency_overrides[get_idempotency_store] = NoReplay
        untouched = Untouched()
        app.dependency_overrides[get_storage] = lambda: untouched
        app.dependency_overrides[get_mailer] = lambda: untouched
        transport = httpx.ASGITransport(app=app)
        outcomes: dict[str, int] = {}
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://api.test",
            headers={"authorization": "Bearer jwt"},
        ) as client:
            for method, path, resource, body in ROUTES:
                url = path.replace("{target}", ids[resource])
                url = url.replace("{incident}", ids[resource]).replace("{tenant_id}", ids[resource])
                response = await client.request(method, url, json=body)
                outcomes[f"{method} {path}"] = response.status_code
                assert ids[resource] not in response.text or response.status_code == 404
        assert {route: status for route, status in outcomes.items() if status != 404} == {}
        assert untouched.calls == []
        # Nada de B mudou.
        async with engine.begin() as connection:
            state = (
                await connection.execute(
                    text(
                        "select (select name from doctor.integrations where id = :integration),"
                        " (select status from doctor.incidents where id = :incident),"
                        " (select role from doctor.memberships where id = :membership),"
                        " (select count(*) from doctor.diagnosis_feedback"
                        "  where diagnosis_id = :diagnosis),"
                        " (select count(*) from doctor.knowledge_documents where id = :document)"
                    ),
                    ids,
                )
            ).one()
        assert tuple(state) == ("Notas", "resolved", "owner", 1, 1)
    finally:
        await drop(engine, ids)
