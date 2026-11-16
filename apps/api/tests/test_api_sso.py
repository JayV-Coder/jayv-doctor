"""SSO pela API (#48): o Owner configura, o domínio se prova por DNS, quem entra pelo IdP ganha
o Vínculo pelo grupo, e o SCIM do IdP desativa o acesso na hora."""

import json
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aid_api.core.auth import Claims, get_claims
from aid_api.main import create_app
from fastapi import FastAPI
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
    """Organização com Owner e Admin; o domínio é único por teste (é único no banco)."""
    ids = {"tenant": str(uuid4()), "owner": str(uuid4()), "admin": str(uuid4())}
    ids["domain"] = f"acme-{ids['tenant'][:8]}.com.br"
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values"
            " (:o, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :eo),"
            " (:a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :ea)",
            "insert into public.organizations (id, name, slug) values (:t, 'SSO', :s)",
            "insert into doctor.tenants (id) values (:t)",
            "insert into public.organization_members (org_id, user_id, role)"
            " values (:t, :o, 'owner'), (:t, :a, 'member')",
            "insert into doctor.memberships (tenant_id, user_id, role)"
            " values (:t, :o, 'owner'), (:t, :a, 'admin')",
        ):
            await connection.execute(
                text(sql),
                {
                    "t": ids["tenant"],
                    "o": ids["owner"],
                    "a": ids["admin"],
                    "s": f"sso-{ids['tenant'][:8]}",
                    "eo": f"owner@{ids['domain']}",
                    "ea": f"admin@{ids['domain']}",
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
            text("delete from auth.users where email like :d"), {"d": f"%@{ids['domain']}"}
        )


def claims(user: str, tenant: str | None, role: str | None, **extra: object) -> Claims:
    raw: dict[str, object] = {"sub": user, "role": "authenticated", "aal": "aal2", **extra}
    if tenant:
        raw |= {"tenant_id": tenant, "tenant_role": role}
    return Claims(sub=user, email=None, aal="aal2", tenant_id=tenant, tenant_role=role, raw=raw)


@pytest_asyncio.fixture
async def app(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    return create_app()


def client_for(app: FastAPI, **headers: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://api.test",
        headers={"authorization": "Bearer jwt", **headers},
    )


async def activate(engine: AsyncEngine, tenant: str) -> str:
    """O que o worker `notifier` faz depois de registrar o provedor e consultar o DNS."""
    provider = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "select doctor.mark_sso_domain(d.id) from doctor.sso_domains d"
                " where d.tenant_id = :t"
            ),
            {"t": tenant},
        )
        await connection.execute(
            text(
                "select doctor.set_sso_provider(c.id, cast(:p as uuid), 'active', null)"
                " from doctor.sso_connections c where c.tenant_id = :t"
            ),
            {"t": tenant, "p": provider},
        )
    return provider


async def idp_groups(engine: AsyncEngine, user: str, provider: str, groups: list[str]) -> None:
    """O que o Supabase Auth grava no login pelo IdP: os atributos SAML na identidade."""
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into auth.identities (provider_id, user_id, identity_data, provider)"
                " values (cast(:u as text), cast(:u as uuid), cast(:d as jsonb), :p)"
                " on conflict (provider_id, provider) do update"
                " set identity_data = excluded.identity_data"
            ),
            {
                "u": user,
                "p": f"sso:{provider}",
                "d": json.dumps({"custom_claims": {"groups": groups}}),
            },
        )


@pytest.mark.asyncio
async def test_owner_configura_dominio_grupos_e_token_scim(
    app: FastAPI, engine: AsyncEngine, org: dict[str, str]
) -> None:
    tenant, domain = org["tenant"], org["domain"]
    async with client_for(app) as client:
        app.dependency_overrides[get_claims] = lambda: claims(org["admin"], tenant, "admin")
        assert (await client.get("/api/v1/sso")).status_code == 403

        app.dependency_overrides[get_claims] = lambda: claims(org["owner"], tenant, "owner")
        empty = await client.get("/api/v1/sso")
        assert empty.json() == {"connection": None, "domains": [], "groups": {}}

        config = {"metadata_url": "https://login.acme.test/metadata.xml", "require_sso": True}
        refused = await client.put("/api/v1/sso", json=config)
        assert (refused.status_code, refused.json()["code"]) == (422, "domain_required")

        added = await client.post("/api/v1/sso/domains", json={"domain": domain.upper()})
        assert added.status_code == 201, added.text
        assert added.json()["domain"] == domain
        assert added.json()["txt_name"] == f"_aid-sso.{domain}"
        assert added.json()["txt_value"].startswith("aid-sso=")
        again = await client.post("/api/v1/sso/domains", json={"domain": domain})
        assert (again.status_code, again.json()["code"]) == (409, "domain_taken")

        configured = await client.put("/api/v1/sso", json=config | {"require_sso": False})
        assert configured.json()["connection"]["status"] == "pending_platform"
        verify = await client.post(f"/api/v1/sso/domains/{added.json()['id']}/verify")
        assert verify.status_code == 202
        async with engine.begin() as connection:
            topics = (
                await connection.scalars(
                    text(
                        "select topic from doctor.outbox_messages where tenant_id = :t"
                        " order by created_at"
                    ),
                    {"t": tenant},
                )
            ).all()
        assert topics == ["sso.sync", "sso.domain"]

        await activate(engine, tenant)
        required = await client.put("/api/v1/sso", json=config)
        assert required.json()["connection"]["require_sso"] is True

        groups = await client.put(
            "/api/v1/sso/groups", json={"groups": {"AID-Analistas": "analyst", "AID-TI": "admin"}}
        )
        assert groups.json()["groups"] == {"AID-Analistas": "analyst", "AID-TI": "admin"}
        owner_group = await client.put("/api/v1/sso/groups", json={"groups": {"x": "owner"}})
        assert owner_group.status_code == 422

        token = await client.post("/api/v1/sso/scim-token", headers={"Idempotency-Key": "scim-1"})
        assert token.json()["token"]
        assert token.json()["base_url"].endswith("/scim/v2")
        replay = await client.post("/api/v1/sso/scim-token", headers={"Idempotency-Key": "scim-1"})
        assert replay.json()["token"] != token.json()["token"]
        settings = await client.get("/api/v1/sso")
        assert settings.json()["connection"]["scim_enabled"] is True
        assert token.json()["token"] not in settings.text


@pytest.mark.asyncio
async def test_descoberta_so_mostra_sso_ativo_com_dominio_verificado(
    app: FastAPI, engine: AsyncEngine, org: dict[str, str]
) -> None:
    tenant, domain = org["tenant"], org["domain"]
    async with client_for(app) as client:
        app.dependency_overrides[get_claims] = lambda: claims(org["owner"], tenant, "owner")
        await client.post("/api/v1/sso/domains", json={"domain": domain})
        await client.put("/api/v1/sso", json={"metadata_url": "https://idp.test/m"})
        before = await client.get("/api/v1/sso/discover", params={"email": f"x@{domain}"})
        assert before.json() == {"sso": False, "required": False, "domain": None}
        await activate(engine, tenant)
        await client.put(
            "/api/v1/sso", json={"metadata_url": "https://idp.test/m", "require_sso": True}
        )

    app.dependency_overrides.clear()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api.test"
    ) as anonymous:
        found = await anonymous.get(
            "/api/v1/sso/discover", params={"email": f"Ana@{domain.upper()}"}
        )
        assert found.json() == {"sso": True, "required": True, "domain": domain}
        other = await anonymous.get("/api/v1/sso/discover", params={"email": "ana@gmail.com"})
        assert other.json()["sso"] is False
        assert (
            await anonymous.get("/api/v1/sso/discover", params={"email": "x"})
        ).status_code == 422


@pytest.mark.asyncio
async def test_login_pelo_idp_cria_o_vinculo_pelo_grupo_mais_alto(
    app: FastAPI, engine: AsyncEngine, org: dict[str, str]
) -> None:
    tenant, domain = org["tenant"], org["domain"]
    async with client_for(app) as client:
        app.dependency_overrides[get_claims] = lambda: claims(org["owner"], tenant, "owner")
        await client.post("/api/v1/sso/domains", json={"domain": domain})
        await client.put("/api/v1/sso", json={"metadata_url": "https://idp.test/m"})
        await client.put(
            "/api/v1/sso/groups",
            json={"groups": {"Leitura": "viewer", "Analistas": "analyst", "Admins": "admin"}},
        )
        provider = await activate(engine, tenant)

        newcomer = str(uuid4())
        async with engine.begin() as connection:
            # O perfil (que o próprio Usuário edita) diz "Admins"; o que vale é o que o IdP
            # gravou na identidade do provedor.
            await connection.execute(
                text(
                    "insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data)"
                    " values (:i, '00000000-0000-0000-0000-000000000000', 'authenticated',"
                    " 'authenticated', :e, cast(:m as jsonb))"
                ),
                {
                    "i": newcomer,
                    "e": f"bia@{domain}",
                    "m": '{"custom_claims": {"groups": ["Admins"]}}',
                },
            )
        await idp_groups(engine, newcomer, provider, ["Leitura", "Analistas", "Outro"])
        amr = [{"method": "sso/saml", "timestamp": 1, "provider": provider}]
        app.dependency_overrides[get_claims] = lambda: claims(newcomer, None, None, amr=amr)
        provisioned = await client.post("/api/v1/sso/provision")
        assert provisioned.json() == {"tenant_id": tenant, "role": "analyst"}

        # Saiu de todos os grupos mapeados (e não há Papel padrão): o Vínculo some de verdade,
        # mesmo com a resposta de erro.
        await idp_groups(engine, newcomer, provider, ["Outro"])
        app.dependency_overrides[get_claims] = lambda: claims(newcomer, None, None, amr=amr)
        no_group = await client.post("/api/v1/sso/provision")
        assert (no_group.status_code, no_group.json()["code"]) == (403, "sso_no_group")
        async with engine.begin() as connection:
            left = await connection.scalar(
                text("select count(*) from doctor.memberships where user_id = :i"), {"i": newcomer}
            )
        assert left == 0

        by_password = [{"method": "password", "timestamp": 1}]
        app.dependency_overrides[get_claims] = lambda: claims(newcomer, None, None, amr=by_password)
        refused = await client.post("/api/v1/sso/provision")
        assert (refused.status_code, refused.json()["code"]) == (403, "sso_inactive")


@pytest.mark.asyncio
async def test_scim_provisiona_e_desativar_tira_o_acesso_na_hora(
    app: FastAPI, engine: AsyncEngine, org: dict[str, str]
) -> None:
    tenant, domain = org["tenant"], org["domain"]
    async with client_for(app) as client:
        app.dependency_overrides[get_claims] = lambda: claims(org["owner"], tenant, "owner")
        await client.put("/api/v1/sso", json={"metadata_url": "https://idp.test/m"})
        token = (await client.post("/api/v1/sso/scim-token")).json()["token"]
    app.dependency_overrides.clear()

    async with client_for(app, authorization=f"Bearer {token}") as idp:
        config = await idp.get("/scim/v2/ServiceProviderConfig")
        assert config.json()["patch"]["supported"] is True

        email = f"admin@{domain}"
        created = await idp.post(
            "/scim/v2/Users",
            json={"schemas": [], "userName": email.upper(), "externalId": "00u1", "active": True},
        )
        assert created.status_code == 201, created.text
        assert created.headers["content-type"].startswith("application/scim+json")
        user = created.json()
        assert (user["userName"], user["externalId"], user["active"]) == (email, "00u1", True)
        duplicate = await idp.post("/scim/v2/Users", json={"userName": email})
        assert (duplicate.status_code, duplicate.json()["scimType"]) == (409, "uniqueness")

        found = await idp.get("/scim/v2/Users", params={"filter": f'userName eq "{email}"'})
        assert found.json()["totalResults"] == 1
        # O IdP reconcilia página por página: o total não muda com a página.
        for index in range(3):
            await idp.post("/scim/v2/Users", json={"userName": f"p{index}@{domain}"})
        second = await idp.get("/scim/v2/Users", params={"startIndex": 3, "count": 2})
        page = second.json()
        assert (page["totalResults"], page["startIndex"], page["itemsPerPage"]) == (4, 3, 2)
        first = await idp.get("/scim/v2/Users", params={"startIndex": 1, "count": 2})
        names = {item["userName"] for item in first.json()["Resources"] + page["Resources"]}
        assert len(names) == 4
        bad = await idp.get("/scim/v2/Users", params={"filter": 'displayName co "a"'})
        assert (bad.status_code, bad.json()["scimType"]) == (400, "invalidFilter")

        # Entra ID: PatchOp com `path: active`. O Admin perde o Vínculo na hora.
        off = await idp.patch(
            f"/scim/v2/Users/{user['id']}",
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "Replace", "path": "active", "value": "False"}],
            },
        )
        assert off.json()["active"] is False
        async with engine.begin() as connection:
            member = await connection.scalar(
                text(
                    "select count(*) from doctor.memberships where tenant_id = :t and user_id = :u"
                ),
                {"t": tenant, "u": org["admin"]},
            )
        assert member == 0

        # Okta: o objeto em `value`.
        on = await idp.patch(
            f"/scim/v2/Users/{user['id']}",
            json={"Operations": [{"op": "replace", "value": {"active": True}}]},
        )
        assert on.json()["active"] is True
        assert (await idp.delete(f"/scim/v2/Users/{user['id']}")).status_code == 204
        gone = await idp.get(f"/scim/v2/Users/{user['id']}")
        assert gone.status_code == 404

    async with client_for(app, authorization="Bearer " + "x" * 40) as stranger:
        denied = await stranger.get("/scim/v2/Users")
        assert denied.status_code == 401
        assert denied.json()["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
