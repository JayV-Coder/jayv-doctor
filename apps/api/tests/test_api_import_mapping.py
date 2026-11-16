"""Mapeamento de colunas e linhas rejeitadas da Importação pela API (#11)."""

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
    ids = {
        "tenant": str(uuid4()),
        "analyst": str(uuid4()),
        "viewer": str(uuid4()),
        "integration": str(uuid4()),
        "import": str(uuid4()),
    }
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values"
            " (:a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :ea),"
            " (:v, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :ev)",
            "insert into public.organizations (id, name, slug) values (:t, 'Mapas', :s)",
            "insert into doctor.tenants (id) values (:t)",
            "insert into public.organization_members (org_id, user_id, role)"
            " values (:t, :a, 'member'), (:t, :v, 'member')",
            "insert into doctor.memberships (tenant_id, user_id, role)"
            " values (:t, :a, 'analyst'), (:t, :v, 'viewer')",
            "insert into doctor.integrations"
            " (id, tenant_id, name, source_system, target_system, environment)"
            " values (:g, :t, 'Pedidos', 'salesforce', 'sap', 'prd')",
            "insert into doctor.imports (id, tenant_id, integration_id, filename, size_bytes,"
            " sha256, format, status, total_lines, rejected)"
            " values (:i, :t, :g, 'sm58.csv', 10, repeat('a', 64), 'csv', 'done', 3, 2)",
            "insert into doctor.import_rejections (tenant_id, import_id, line_number, reason)"
            " values (:t, :i, 3, 'linha sem data (timestamp)'),"
            " (:t, :i, 2, 'JSON inválido; \"x\"')",
        ):
            await connection.execute(
                text(sql),
                {
                    "t": ids["tenant"],
                    "a": ids["analyst"],
                    "v": ids["viewer"],
                    "g": ids["integration"],
                    "i": ids["import"],
                    "s": f"mapas-{ids['tenant'][:8]}",
                    "ea": f"{ids['analyst']}@a.test",
                    "ev": f"{ids['viewer']}@a.test",
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
            {"a": ids["analyst"], "v": ids["viewer"]},
        )


def as_member(user: str, tenant: str, role: str) -> Claims:
    raw = {
        "sub": user,
        "role": "authenticated",
        "aal": "aal1",
        "tenant_id": tenant,
        "tenant_role": role,
    }
    return Claims(sub=user, email=None, aal="aal1", tenant_id=tenant, tenant_role=role, raw=raw)


@pytest.mark.asyncio
async def test_mapeamento_sugerido_salvo_e_lido_pela_integracao(
    engine: AsyncEngine, org: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    app = create_app()
    path = f"/api/v1/imports/mappings/{org['integration']}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://api.test",
        headers={"authorization": "Bearer jwt"},
    ) as client:
        app.dependency_overrides[get_claims] = lambda: as_member(
            org["analyst"], org["tenant"], "analyst"
        )
        empty = await client.get(path)
        assert empty.json()["columns"] == {}
        assert "timestamp" in empty.json()["fields"]

        header = ["Data", "MSGTY", "Texto", "Cliente"]
        suggestion = await client.post(
            "/api/v1/imports/mapping-suggestion", json={"columns": header}
        )
        assert suggestion.json() == {
            "columns": {"timestamp": "Data", "severity": "MSGTY", "message": "Texto"}
        }

        chosen = {"timestamp": "Data", "message": "Texto", "operation": "Cliente"}
        saved = await client.put(path, json={"columns": chosen})
        assert saved.status_code == 200, saved.text
        assert (await client.get(path)).json()["columns"] == chosen
        bad = await client.put(path, json={"columns": {"cliente": "Cliente"}})
        assert bad.status_code == 422
        missing = await client.put(f"/api/v1/imports/mappings/{uuid4()}", json={"columns": {}})
        assert missing.status_code == 404

        app.dependency_overrides[get_claims] = lambda: as_member(
            org["viewer"], org["tenant"], "viewer"
        )
        assert (await client.get(path)).json()["columns"] == chosen
        assert (await client.put(path, json={"columns": {}})).status_code == 403


@pytest.mark.asyncio
async def test_linhas_rejeitadas_saem_em_csv_na_ordem_do_arquivo(
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
        app.dependency_overrides[get_claims] = lambda: as_member(
            org["viewer"], org["tenant"], "viewer"
        )
        response = await client.get(f"/api/v1/imports/{org['import']}/rejections")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "rejeitadas-sm58.csv" in response.headers["content-disposition"]
        assert response.text.splitlines() == [
            "linha,motivo",
            '2,"JSON inválido; ""x"""',
            "3,linha sem data (timestamp)",
        ]
        other = await client.get(f"/api/v1/imports/{uuid4()}/rejections")
        assert other.status_code == 404
