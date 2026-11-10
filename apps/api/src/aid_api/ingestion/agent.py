"""Agente local (ticket #39, ADR-0015): identidade e prova de cada requisição.

O agente se apresenta com o segredo dele (`Authorization: Bearer aid_agt_…`, só o hash no banco)
e assina cada requisição com a chave Ed25519 que ele mesmo gerou:

    assinatura = Ed25519(f"{método}\\n{caminho[?query]}\\n{timestamp}\\n{sha256(corpo)}")

nos cabeçalhos `X-AID-Timestamp` (segundos Unix) e `X-AID-Signature` (base64). A API confere a
assinatura com a chave pública registrada e o banco confere o status a cada chamada: revogado
é recusado na próxima requisição.
"""

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.x509.oid import NameOID
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import bindparam

from aid_api.core.db import anonymous_tx
from aid_api.core.errors import ApiError

SECRET_PREFIX = "aid_agt_"  # noqa: S105 - prefixo, não segredo
SKEW_SECONDS = 300
CERT_DAYS = 90


def unauthorized() -> ApiError:
    return ApiError(
        401, "invalid_agent", "Agente não reconhecido, revogado ou assinatura inválida."
    )


ERRORS = {
    "DR070": lambda: ApiError(
        401, "invalid_registration", "Token de registro inválido ou vencido."
    ),
    "DR071": unauthorized,
    "DR050": lambda: ApiError(429, "quota_exceeded", "A Cota de Eventos do mês foi esgotada."),
}


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    tenant_id: str
    integration_id: str
    secret_hash: str
    public_key: str
    config: dict[str, Any]
    config_version: int


def secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def signed_target(path: str, query: str) -> str:
    """O que a assinatura cobre da URL: caminho e query, como foram enviados."""
    return f"{path}?{query}" if query else path


def signed_message(method: str, path: str, timestamp: str, body: bytes) -> bytes:
    return f"{method.upper()}\n{path}\n{timestamp}\n{hashlib.sha256(body).hexdigest()}".encode()


def public_key(encoded: str) -> Ed25519PublicKey:
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) != 32:
        raise ValueError("chave Ed25519 tem 32 bytes")
    return Ed25519PublicKey.from_public_bytes(raw)


def verify(
    encoded_key: str,
    method: str,
    path: str,
    timestamp: str,
    signature: str,
    body: bytes,
    now: float | None = None,
) -> None:
    try:
        moment = int(timestamp)
        if abs((now or time.time()) - moment) > SKEW_SECONDS:
            raise unauthorized()
        public_key(encoded_key).verify(
            base64.b64decode(signature, validate=True),
            signed_message(method, path, timestamp, body),
        )
    except (ValueError, InvalidSignature) as exc:
        raise unauthorized() from exc


def fingerprint(encoded_key: str) -> str:
    return hashlib.sha256(base64.b64decode(encoded_key)).hexdigest()


def certificate(agent_id: str, encoded_key: str) -> str | None:
    """Certificado X.509 do agente, assinado pela CA da plataforma (`AID_AGENT_CA_KEY` e
    `AID_AGENT_CA_CERT`, do Secret Manager), para o mTLS no balanceador. Sem a CA configurada
    (local, E2E), não há certificado: a assinatura das requisições continua obrigatória."""
    ca_key_pem, ca_cert_pem = (
        os.environ.get("AID_AGENT_CA_KEY"),
        os.environ.get("AID_AGENT_CA_CERT"),
    )
    if not ca_key_pem or not ca_cert_pem:
        return None
    ca_key = serialization.load_pem_private_key(ca_key_pem.encode(), password=None)
    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode())
    now = datetime.now(UTC)
    built = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"agent:{agent_id}")]))
        .issuer_name(ca_cert.subject)
        .public_key(public_key(encoded_key))
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CERT_DAYS))
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())  # type: ignore[arg-type]
    )
    return built.public_bytes(serialization.Encoding.PEM).decode()


def release() -> dict[str, Any] | None:
    """Manifesto da versão nova do agente (`AID_AGENT_RELEASE`, posto pelo deploy): versão, URL,
    sha256 e a assinatura Ed25519 da chave de release, que o agente confere antes de aplicar."""
    raw = os.environ.get("AID_AGENT_RELEASE")
    if not raw:
        return None
    try:
        found = json.loads(raw)
    except ValueError:
        return None
    return (
        found
        if isinstance(found, dict) and {"version", "url", "sha256", "signature"} <= found.keys()
        else None
    )


class AgentRepository:
    async def register(
        self, token: str, encoded_key: str, version: str
    ) -> tuple[str, str, str | None]:
        """(agent_id, segredo novo, certificado). O segredo só aparece aqui."""
        try:
            fingerprint_hex = fingerprint(encoded_key)
            public_key(encoded_key)
        except ValueError as exc:
            raise ApiError(422, "validation_error", "Chave pública Ed25519 inválida.") from exc
        secret = SECRET_PREFIX + secrets.token_urlsafe(32)
        async with anonymous_tx(ERRORS) as connection:
            row = (
                await connection.execute(
                    text("select agent_id::text from doctor.register_agent(:t, :s, :k, :f, :v)"),
                    {
                        "t": secret_hash(token),
                        "s": secret_hash(secret),
                        "k": encoded_key,
                        "f": fingerprint_hex,
                        "v": version,
                    },
                )
            ).one()
        return row.agent_id, secret, certificate(row.agent_id, encoded_key)

    async def identify(self, hashed: str) -> AgentIdentity:
        async with anonymous_tx(ERRORS) as connection:
            row = (
                await connection.execute(
                    text(
                        "select agent_id::text, tenant_id::text, integration_id::text, public_key,"
                        " config, config_version from doctor.resolve_agent(:h)"
                    ),
                    {"h": hashed},
                )
            ).first()
        if row is None:
            raise unauthorized()
        return AgentIdentity(
            row.agent_id,
            row.tenant_id,
            row.integration_id,
            hashed,
            row.public_key,
            dict(row.config),
            row.config_version,
        )

    async def seen(self, hashed: str, version: str) -> None:
        async with anonymous_tx(ERRORS) as connection:
            await connection.execute(
                text("select doctor.agent_seen(:h, :v)"), {"h": hashed, "v": version}
            )

    async def accept(self, hashed: str, events: list[dict[str, Any]]) -> str:
        async with anonymous_tx(ERRORS) as connection:
            statement = text("select doctor.accept_agent_batch(:h, :events)::text").bindparams(
                bindparam("events", type_=JSONB)
            )
            return str(await connection.scalar(statement, {"h": hashed, "events": events}))

    async def claim_llm(self, hashed: str) -> tuple[str, dict[str, Any], int] | None:
        """O próximo pedido ao modelo local desta Organização para este agente (#46)."""
        async with anonymous_tx(ERRORS) as connection:
            found = (
                await connection.execute(
                    text(
                        "select id::text, request, timeout_seconds from doctor.claim_local_llm(:h)"
                    ),
                    {"h": hashed},
                )
            ).first()
        return (str(found.id), dict(found.request), int(found.timeout_seconds)) if found else None

    async def finish_llm(
        self, hashed: str, request: str, response: dict[str, Any] | None, error: str | None
    ) -> bool:
        async with anonymous_tx(ERRORS) as connection:
            statement = text(
                "select doctor.finish_local_llm(:h, cast(:r as uuid), :response, :e)"
            ).bindparams(bindparam("response", type_=JSONB))
            return bool(
                await connection.scalar(
                    statement, {"h": hashed, "r": request, "response": response, "e": error}
                )
            )


def get_agent_repository() -> AgentRepository:
    return AgentRepository()
