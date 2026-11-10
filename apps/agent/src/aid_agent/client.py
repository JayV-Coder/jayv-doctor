"""Cliente da plataforma: só chamadas de saída por HTTPS, assinadas com a chave do agente. Com o
certificado do registro, apresenta-o também no TLS (mTLS no balanceador)."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aid_agent.identity import CERT_FILE, KEY_FILE, Credentials, signature_headers


class PlatformError(Exception):
    """A plataforma recusou o agente (revogado, segredo ou assinatura inválidos): parar."""


class BatchRejectedError(Exception):
    """A plataforma recusou o lote inteiro (413, 422): reenviar igual não adianta."""

    def __init__(self, status: int) -> None:
        super().__init__(f"lote recusado: HTTP {status}")
        self.status = status


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
        # A assinatura cobre caminho e query, exatamente como vão na URL.
        target = f"{path}?{urlencode(params)}" if params else path
        headers = signature_headers(self.key, self.credentials.secret, method, target, content)
        if body is not None:
            headers["content-type"] = "application/json"
        response = self.http.request(method, target, content=content, headers=headers)
        if response.status_code in (401, 403):
            raise PlatformError("a plataforma recusou o agente (revogado ou assinatura inválida)")
        return response

    def config(self, known_version: int, version: str) -> dict[str, Any] | None:
        """Long-poll da config; a chamada é também o sinal de vida, com a versão do agente."""
        response = self.request(
            "GET",
            "/api/v1/agent/config",
            params={"known_version": known_version, "version": version},
        )
        if response.status_code == 304:
            return None
        response.raise_for_status()
        return dict(response.json())

    def send(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        response = self.request("POST", "/api/v1/agent/events", {"events": events})
        if 400 <= response.status_code < 500 and response.status_code != 429:
            raise BatchRejectedError(response.status_code)
        response.raise_for_status()
        return dict(response.json())


class LocalModel:
    """As rotas do modelo local (#46) num cliente à parte: a thread do modelo não divide a
    conexão com a coleta."""

    def __init__(self, platform: Platform) -> None:
        self.platform = platform

    def next(self) -> dict[str, Any] | None:
        """Long-poll (até 25 s) do próximo pedido da plataforma."""
        response = self.platform.request("GET", "/api/v1/agent/llm")
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return dict(response.json())

    def answer(self, request: str, result: dict[str, Any]) -> None:
        response = self.platform.request("POST", f"/api/v1/agent/llm/{request}", result)
        if response.status_code != 404:
            response.raise_for_status()


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
