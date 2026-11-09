"""Cliente da plataforma: só chamadas de saída por HTTPS, assinadas com a chave do agente. Com o
certificado do registro, apresenta-o também no TLS (mTLS no balanceador)."""

import json
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aid_agent.identity import CERT_FILE, KEY_FILE, Credentials, signature_headers


class PlatformError(Exception):
    """A plataforma recusou (4xx): repetir igual não adianta."""


class Platform:
    def __init__(
        self,
        credentials: Credentials,
        key: Ed25519PrivateKey,
        state: Path | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.credentials = credentials
        self.key = key
        cert = None
        if state is not None and (state / CERT_FILE).exists():
            cert = (str(state / CERT_FILE), str(state / KEY_FILE))
        self.http = httpx.Client(
            base_url=credentials.api_url.rstrip("/"),
            transport=transport,
            cert=cert,
            timeout=httpx.Timeout(40.0),
        )

    def request(
        self, method: str, path: str, body: Any = None, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        content = b"" if body is None else json.dumps(body).encode()
        headers = signature_headers(self.key, self.credentials.secret, method, path, content)
        if body is not None:
            headers["content-type"] = "application/json"
        response = self.http.request(method, path, content=content, headers=headers, params=params)
        if response.status_code in (401, 403):
            raise PlatformError("a plataforma recusou o agente (revogado ou assinatura inválida)")
        return response

    def config(self, known_version: int) -> dict[str, Any] | None:
        response = self.request(
            "GET", "/api/v1/agent/config", params={"known_version": known_version}
        )
        if response.status_code == 304:
            return None
        response.raise_for_status()
        return dict(response.json())

    def heartbeat(self, version: str) -> None:
        self.request("POST", "/api/v1/agent/heartbeat", {"version": version}).raise_for_status()

    def send(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        response = self.request("POST", "/api/v1/agent/events", {"events": events})
        if 400 <= response.status_code < 500 and response.status_code != 429:
            raise PlatformError(f"lote recusado: HTTP {response.status_code}")
        response.raise_for_status()
        return dict(response.json())


def register(
    api_url: str,
    token: str,
    public_key: str,
    version: str,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    with httpx.Client(
        base_url=api_url.rstrip("/"), transport=transport, timeout=httpx.Timeout(30.0)
    ) as http:
        response = http.post(
            "/api/v1/agent/register",
            json={"token": token, "public_key": public_key, "version": version},
        )
    if response.status_code == 401:
        raise PlatformError("token de registro inválido ou vencido")
    response.raise_for_status()
    return dict(response.json())
