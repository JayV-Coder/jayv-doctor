"""Agente local (ticket #39): registro, requisições assinadas, revogação e config da allowlist."""

import base64
import hashlib
import json
import os
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aid_api.agents.config import validate
from aid_api.core.auth import Claims, get_claims
from aid_api.core.errors import ApiError
from aid_api.ingestion.agent import signed_message, verify
from aid_api.main import create_app
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")


def raw_public(key: Ed25519PrivateKey) -> str:
    return base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()


def signed(
    key: Ed25519PrivateKey,
    secret: str,
    method: str,
    path: str,
    body: bytes,
    at: float | None = None,
) -> dict[str, str]:
    timestamp = str(int(at if at is not None else time.time()))
    signature = base64.b64encode(key.sign(signed_message(method, path, timestamp, body))).decode()
    return {
        "authorization": f"Bearer {secret}",
        "x-aid-timestamp": timestamp,
        "x-aid-signature": signature,
        "content-type": "application/json",
    }


def test_assinatura_alterada_vencida_ou_de_outra_chave_e_recusada() -> None:
    key, other = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    body = b'{"events": []}'
    now = time.time()
    good = signed(key, "s", "POST", "/api/v1/agent/events", body, now)
    verify(
        raw_public(key),
        "POST",
        "/api/v1/agent/events",
        good["x-aid-timestamp"],
        good["x-aid-signature"],
        body,
        now,
    )
    events, config = "/api/v1/agent/events", "/api/v1/agent/config"
    stamp, signature = good["x-aid-timestamp"], good["x-aid-signature"]
    cases = [
        (raw_public(key), events, b"{}", now),  # corpo alterado
        (raw_public(key), config, body, now),  # outro caminho
        (raw_public(other), events, body, now),  # outra chave
        (raw_public(key), events, body, now + 600),  # fora da janela de 5 min
    ]
    for public, path, payload, moment in cases:
        with pytest.raises(ApiError) as raised:
            verify(public, "POST", path, stamp, signature, payload, moment)
        assert raised.value.status == 401


def test_config_so_da_allowlist() -> None:
    ok = validate(
        {
            "collections": [
                {"type": "directory", "path": "/exports/sm58", "pattern": "*.csv"},
                {"type": "rfc_table", "table": "EDIDS"},
                {"type": "rfc_function", "name": "Z_AID_READ_SLG1"},
            ]
        }
    )
    assert ok["collections"][1]["fields"][0] == "DOCNUM"
    for bad in (
        {"collections": [{"type": "rfc_table", "table": "USR02"}]},
        {
            "collections": [
                {"type": "rfc_table", "table": "EDIDC", "fields": ["DOCNUM", "PASSCODE"]}
            ]
        },
        {"collections": [{"type": "rfc_function", "name": "RFC_READ_TABLE"}]},
        {"collections": [{"type": "directory", "path": "/exports/../etc"}]},
        {"collections": [{"type": "directory", "path": "relativo/dir"}]},
        {"collections": [{"type": "shell", "command": "ls"}]},
    ):
        with pytest.raises(ApiError):
            validate(bad)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


@pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
@pytest.mark.asyncio
async def test_registro_lote_assinado_e_revogacao_na_proxima_chamada(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.core import db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    tenant, integration, user = str(uuid4()), str(uuid4()), str(uuid4())
    async with engine.begin() as connection:
        for sql in (
            "insert into auth.users (id, instance_id, aud, role, email) values (:u,"
            " '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :e)",
            "insert into public.organizations (id, name, slug) values (:t, 'Agente', :s)",
            "insert into doctor.tenants (id) values (:t)",
            "insert into public.organization_members (org_id, user_id, role)"
            " values (:t, :u, 'member')",
            "insert into doctor.memberships (tenant_id, user_id, role) values (:t, :u, 'admin')",
            "insert into doctor.integrations (id, tenant_id, name, source_system, target_system,"
            " environment) values (:i, :t, 'IDocs', 'sap', 'gcp', 'prd')",
        ):
            await connection.execute(
                text(sql),
                {
                    "t": tenant,
                    "i": integration,
                    "u": user,
                    "s": f"agente-{tenant[:8]}",
                    "e": f"{user}@a.test",
                },
            )
    raw = {
        "sub": user,
        "role": "authenticated",
        "aal": "aal2",
        "tenant_id": tenant,
        "tenant_role": "admin",
    }
    claims = Claims(
        sub=user, email=None, aal="aal2", tenant_id=tenant, tenant_role="admin", raw=raw
    )
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: claims
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://api.test",
            headers={"authorization": "Bearer jwt"},
        ) as admin:
            created = await admin.post(
                "/api/v1/agents",
                json={
                    "name": "SAP ECC Campinas",
                    "integration_id": integration,
                    "config": {"collections": [{"type": "rfc_table", "table": "EDIDS"}]},
                },
            )
            assert created.status_code == 201, created.text
            token = created.json()["registration_token"]
            assert token in created.json()["install_command"]
        anonymous = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=anonymous), base_url="http://api.test"
        ) as agent:
            key = Ed25519PrivateKey.generate()
            registered = await agent.post(
                "/api/v1/agent/register",
                json={"token": token, "public_key": raw_public(key), "version": "0.1.0"},
            )
            assert registered.status_code == 201, registered.text
            secret = registered.json()["secret"]
            again = await agent.post(
                "/api/v1/agent/register",
                json={"token": token, "public_key": raw_public(key), "version": "0.1.0"},
            )
            assert again.status_code == 401
            event = {
                "schema_version": "1.0",
                "event_id": "0192e1c4-7b2c-7d4e-8f00-123456789abc",
                "integration_id": integration,
                "timestamp": datetime.now(UTC).isoformat(),
                "source": {"provider": "sap", "service": "ECC"},
                "operation": "IDOC_STATUS",
                "severity": "ERROR",
                "error": {"category": "UNKNOWN", "code": "IDOC 51"},
            }
            body = json.dumps({"events": [event]}).encode()
            sent = await agent.post(
                "/api/v1/agent/events",
                content=body,
                headers=signed(key, secret, "POST", "/api/v1/agent/events", body),
            )
            assert sent.status_code == 202, sent.text
            assert sent.json()["accepted"] == 1
            config = await agent.get(
                "/api/v1/agent/config",
                headers=signed(key, secret, "GET", "/api/v1/agent/config", b""),
            )
            assert config.json()["config"]["collections"][0]["table"] == "EDIDS"
            forged = await agent.post(
                "/api/v1/agent/events",
                content=body,
                headers=signed(
                    Ed25519PrivateKey.generate(), secret, "POST", "/api/v1/agent/events", body
                ),
            )
            assert forged.status_code == 401

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://api.test",
                headers={"authorization": "Bearer jwt"},
            ) as admin:
                listed = (await admin.get("/api/v1/agents")).json()
                assert (listed[0]["status"], listed[0]["version"]) == ("active", "0.1.0")
                assert (
                    listed[0]["cert_fingerprint"]
                    == hashlib.sha256(base64.b64decode(raw_public(key))).hexdigest()
                )
                started = time.monotonic()
                assert (
                    await admin.post(f"/api/v1/agents/{listed[0]['id']}/revoke")
                ).status_code == 204
            refused = await agent.post(
                "/api/v1/agent/events",
                content=body,
                headers=signed(key, secret, "POST", "/api/v1/agent/events", body),
            )
            assert refused.status_code == 401
            # Critério do ticket: revogado recusado em menos de 1 min (aqui, na chamada seguinte).
            assert time.monotonic() - started < 60
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("delete from doctor.tenants where id = :t"), {"t": tenant}
            )
            await connection.execute(
                text("delete from public.organizations where id = :t"), {"t": tenant}
            )
            await connection.execute(text("delete from auth.users where id = :u"), {"u": user})
