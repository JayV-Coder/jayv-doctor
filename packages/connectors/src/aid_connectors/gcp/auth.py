"""Token de acesso ao Cloud Logging com a chave de Service Account do cliente (no Vault), trocada
por um token com um JWT assinado (RFC 7523), sem SDK do Google.

O modo sem chave (impersonation de uma Service Account do cliente pela conta da plataforma) fica
desligado: com uma conta de plataforma só para todas as Organizações, uma Organização poderia
nomear a Service Account de outra e ler os logs dela (confused deputy). Ver
docs/operations/conectores.md.
"""

import json
import os
import time
from collections.abc import Mapping
from typing import Any

import httpx
import jwt

from aid_connectors.base import ConnectorError, Secret

SCOPE = "https://www.googleapis.com/auth/logging.read"
# Sempre este endpoint: o `token_uri` do JSON vem do cliente e levaria a plataforma a postar onde
# ele quisesse (SSRF). A variável é da plataforma, só para os testes ponta a ponta.
OAUTH_ENDPOINT = os.environ.get("AID_GCP_OAUTH_URL", "https://oauth2.googleapis.com/token")


def service_account(secret: Secret) -> Mapping[str, Any]:
    try:
        info = json.loads(secret.reveal())
    except ValueError:
        info = None
    if not isinstance(info, dict) or not {"client_email", "private_key"} <= info.keys():
        raise ConnectorError("auth", "A credencial não é um JSON de Service Account do Google.")
    return info


def principal(secret: Secret) -> str:
    """Quem lê os logs, para a mensagem de permissão dizer a quem conceder."""
    return str(service_account(secret)["client_email"])


async def access_token(client: httpx.AsyncClient, secret: Secret) -> tuple[str, float]:
    """(token, segundos de validade)."""
    info = service_account(secret)
    now = int(time.time())
    try:
        assertion = jwt.encode(
            {
                "iss": info["client_email"],
                "scope": SCOPE,
                "aud": OAUTH_ENDPOINT,
                "iat": now,
                "exp": now + 3600,
            },
            info["private_key"],
            algorithm="RS256",
        )
    except (ValueError, TypeError, jwt.PyJWTError) as exc:
        raise ConnectorError("auth", "A chave privada da Service Account é inválida.") from exc
    try:
        response = await client.post(
            OAUTH_ENDPOINT,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
    except httpx.HTTPError as exc:
        raise ConnectorError("transient", "O Google não respondeu ao pedido de token.") from exc
    if response.status_code in (400, 401):
        raise ConnectorError("auth", "O Google recusou a chave da Service Account.")
    try:
        body = response.json()
        return str(body["access_token"]), float(body.get("expires_in", 3600))
    except (ValueError, KeyError) as exc:
        raise ConnectorError(
            "transient", "Resposta inesperada do Google ao pedir o token."
        ) from exc
