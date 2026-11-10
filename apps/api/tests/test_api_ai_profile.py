"""Perfil de IA pela API (#45): Owner com MFA troca; o dedicado é contratado; a tela vê a
verificação diária e o progresso do reindex."""

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


@pytest.mark.asyncio
async def test_owner_passa_para_o_brasil_e_ve_verificacao_e_reindex(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    tenant, owner, admin, document = (str(uuid4()) for _ in range(4))
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values"
            " (:o, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated',"
            " :eo), (:a, '00000000-0000-0000-0000-000000000000', 'authenticated',"
            " 'authenticated', :ea)",
            "insert into public.organizations (id, name, slug) values (:t, 'IA', :s)",
            "insert into doctor.tenants (id) values (:t)",
            "insert into public.organization_members (org_id, user_id, role)"
            " values (:t, :o, 'owner'), (:t, :a, 'member')",
            "insert into doctor.memberships (tenant_id, user_id, role)"
            " values (:t, :o, 'owner'), (:t, :a, 'admin')",
            "insert into doctor.knowledge_documents (id, tenant_id, title, source,"
            " content_type, size_bytes, storage_path, status, embedding_model, chunk_count)"
            " values (:d, :t, 'Runbook', 'upload', 'text/markdown', 10, :p, 'ready',"
            " 'voyage-3', 1)",
            "insert into doctor.ai_profile_checks (profile, ok, hosts, region) values"
            " ('br_region', true, '{southamerica-east1-aiplatform.googleapis.com}',"
            " 'southamerica-east1')",
        ):
            await connection.execute(
                text(sql),
                {
                    "t": tenant,
                    "o": owner,
                    "a": admin,
                    "d": document,
                    "s": f"ia-{tenant[:8]}",
                    "p": f"{tenant}/{document}/r.md",
                    "eo": f"{owner}@a.test",
                    "ea": f"{admin}@a.test",
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
            denied = await client.put("/api/v1/privacy/ai-profile", json={"profile": "br_region"})
            assert denied.status_code == 403

            app.dependency_overrides[get_claims] = lambda: as_role(owner, "owner")
            dedicated = await client.put(
                "/api/v1/privacy/ai-profile", json={"profile": "dedicated"}
            )
            assert (dedicated.status_code, dedicated.json()["code"]) == (
                422,
                "dedicated_by_contract",
            )
            changed = await client.put("/api/v1/privacy/ai-profile", json={"profile": "br_region"})
            assert changed.status_code == 204, changed.text
            settings = (await client.get("/api/v1/privacy")).json()
            assert (settings["ai_profile"], settings["llm_provider"]) == ("br_region", "vertex")
            assert settings["ai_check"]["region"] == "southamerica-east1"
            # O runbook está no índice do Voyage: falta reindexar para o do Vertex.
            assert settings["reindex"] == {"model": "text-embedding-005", "total": 1, "current": 0}
    finally:
        async with engine.begin() as connection:
            await connection.execute(text("delete from doctor.ai_profile_checks"))
            await connection.execute(
                text("delete from doctor.tenants where id = :t"), {"t": tenant}
            )
            await connection.execute(
                text("delete from public.organizations where id = :t"), {"t": tenant}
            )
            await connection.execute(
                text("delete from auth.users where id = any(cast(:u as uuid[]))"),
                {"u": [owner, admin]},
            )
