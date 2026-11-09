"""Token do Salesforce com a Connected App do cliente (ticket #37), sem senha de Usuário.

- **JWT Bearer** (recomendado): o Doctor assina um JWT (RS256) com a chave privada do
  certificado da Connected App, guardada no Vault (`{"client_id", "username", "private_key"}`).
- **Web Server Flow:** o refresh token obtido na autorização fica no Vault
  (`{"client_id", "client_secret", "refresh_token"}`).

O token vai sempre para o host de login conhecido (produção ou sandbox), nunca para um endereço
vindo do cliente, e o `instance_url` da resposta precisa ser do Salesforce (SSRF)."""

import json
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
import jwt

from aid_connectors.base import ConnectorError, Secret
from aid_connectors.common import is_loopback

LOGIN = {"production": "https://login.salesforce.com", "sandbox": "https://test.salesforce.com"}
INSTANCE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.(salesforce|force)\.com$")


@dataclass(frozen=True)
class Session:
    token: str
    instance_url: str
    expires_at: float


def login_url(environment: str, environ: Mapping[str, str] = os.environ) -> str:
    """`AID_SF_LOGIN_URL` só existe para o Salesforce falso do E2E e só aceita loopback."""
    override = environ.get("AID_SF_LOGIN_URL")
    if override:
        if not is_loopback(override):
            raise ValueError("endpoint do Salesforce trocado só pode ser loopback (E2E)")
        return override.rstrip("/")
    return LOGIN[environment]


def trusted_instance(url: str, login: str) -> str:
    parsed = urlparse(url)
    if is_loopback(login) and is_loopback(url):
        return url.rstrip("/")
    if (
        parsed.scheme != "https"
        or not INSTANCE.match(parsed.hostname or "")
        or parsed.path not in ("", "/")
    ):
        raise ConnectorError("auth", "O Salesforce devolveu uma instância inesperada.")
    return f"https://{parsed.hostname}"


def credential(secret: Secret, auth: str) -> Mapping[str, str]:
    try:
        info = json.loads(secret.reveal())
    except ValueError:
        info = None
    needed = (
        {"client_id", "username", "private_key"}
        if auth == "jwt_bearer"
        else {"client_id", "client_secret", "refresh_token"}
    )
    if not isinstance(info, dict) or not needed <= info.keys():
        raise ConnectorError("auth", "A credencial não tem os campos da Connected App.")
    return {key: str(info[key]) for key in needed}


async def session(client: httpx.AsyncClient, secret: Secret, config: Mapping[str, Any]) -> Session:
    auth = str(config.get("auth", "jwt_bearer"))
    login = login_url(str(config.get("environment", "production")))
    info = credential(secret, auth)
    if auth == "jwt_bearer":
        now = int(time.time())
        try:
            assertion = jwt.encode(
                # aud é o host de login, mesmo no E2E: é o que o Salesforce confere.
                {"iss": info["client_id"], "sub": info["username"], "aud": login, "exp": now + 180},
                info["private_key"],
                algorithm="RS256",
            )
        except (ValueError, TypeError, jwt.PyJWTError) as exc:
            raise ConnectorError("auth", "A chave privada do certificado é inválida.") from exc
        data = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}
    else:
        data = {
            "grant_type": "refresh_token",
            "client_id": info["client_id"],
            "client_secret": info["client_secret"],
            "refresh_token": info["refresh_token"],
        }
    try:
        response = await client.post(f"{login}/services/oauth2/token", data=data)
    except httpx.HTTPError as exc:
        raise ConnectorError("transient", "O Salesforce não respondeu ao pedido de token.") from exc
    if response.status_code in (400, 401):
        # invalid_grant: certificado, usuário não pré-autorizado na Connected App ou refresh
        # token revogado. A mensagem do Salesforce não volta (pode citar o usuário).
        raise ConnectorError("auth", "O Salesforce recusou a credencial da Connected App.")
    try:
        body = response.json()
        token, instance = str(body["access_token"]), str(body["instance_url"])
    except (ValueError, KeyError) as exc:
        raise ConnectorError(
            "transient", "Resposta inesperada do Salesforce ao pedir o token."
        ) from exc
    # O Salesforce não diz a validade; a sessão padrão é de 2 h, e o token é renovado antes.
    return Session(token, trusted_instance(instance, login), time.monotonic() + 3600)
