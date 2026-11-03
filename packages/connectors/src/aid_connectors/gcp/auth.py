"""Token de acesso ao Cloud Logging, sem SDK do Google.

- `key`: JSON de Service Account do cliente (no Vault), trocado por token com um JWT assinado
  (RFC 7523).
- `impersonation` (preferido, sem chave): a conta de serviço da plataforma, pelo metadata server do
  Cloud Run, pede um token para a Service Account do cliente, que deu a ela
  `roles/iam.serviceAccountTokenCreator`.
"""

import json
import time
from collections.abc import Mapping
from typing import Any

import httpx
import jwt

from aid_connectors.base import ConnectorError, Secret

SCOPE = "https://www.googleapis.com/auth/logging.read"
OAUTH_ENDPOINT = "https://oauth2.googleapis.com/token"
METADATA_ACCESS = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
IMPERSONATE = "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{account}:generateAccessToken"


def service_account(secret: Secret) -> Mapping[str, Any]:
    try:
        info = json.loads(secret.reveal())
    except ValueError:
        info = None
    if not isinstance(info, dict) or not {"client_email", "private_key"} <= info.keys():
        raise ConnectorError("auth", "A credencial não é um JSON de Service Account do Google.")
    return info


def principal(secret: Secret, config: Mapping[str, Any]) -> str:
    """Quem lê os logs, para a mensagem de permissão dizer exatamente a quem conceder."""
    if config.get("auth") == "impersonation":
        return str(config["service_account"])
    return str(service_account(secret)["client_email"])


async def access_token(client: httpx.AsyncClient, secret: Secret, config: Mapping[str, Any]) -> str:
    if config.get("auth") == "impersonation":
        return await impersonated(client, str(config["service_account"]))
    info = service_account(secret)
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": info["client_email"],
            "scope": SCOPE,
            "aud": info.get("token_uri", OAUTH_ENDPOINT),
            "iat": now,
            "exp": now + 3600,
        },
        info["private_key"],
        algorithm="RS256",
    )
    response = await client.post(
        info.get("token_uri", OAUTH_ENDPOINT),
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
    )
    if response.status_code != 200:
        raise ConnectorError("auth", "O Google recusou a chave da Service Account.")
    return str(response.json()["access_token"])


async def impersonated(client: httpx.AsyncClient, account: str) -> str:
    own = await client.get(METADATA_ACCESS, headers={"Metadata-Flavor": "Google"})
    if own.status_code != 200:
        raise ConnectorError("transient", "Credencial da plataforma indisponível.")
    response = await client.post(
        IMPERSONATE.format(account=account),
        json={"scope": [SCOPE], "lifetime": "3600s"},
        headers={"authorization": f"Bearer {own.json()['access_token']}"},
    )
    if response.status_code == 403:
        raise ConnectorError(
            "auth",
            f"A plataforma não pode agir como {account}: conceda a ela "
            "roles/iam.serviceAccountTokenCreator nessa Service Account.",
        )
    if response.status_code != 200:
        raise ConnectorError("transient", "O Google não emitiu o token da Service Account.")
    return str(response.json()["accessToken"])
