"""Conector OData genérico, só de consulta (ticket #40): o enriquecimento pergunta a um serviço
OData (S/4HANA `API_SALES_ORDER_SRV`, um ECC exposto pelo gateway ou pela BTP) se o registro
existe. Não coleta Eventos: a Sincronização não roda para ele.

- **Endereço:** `service_url` só HTTPS, sem usuário na URL, e o host precisa resolver só para
  endereços públicos (SSRF). A conferência acontece na própria conexão: o transporte resolve o
  nome, confere e conecta no endereço conferido (o TLS continua validando o nome), então um DNS
  que muda de resposta entre a conferência e a conexão (rebinding) não leva a rede interna.
  Loopback só com `AID_ODATA_ALLOW_LOOPBACK=1`, que existe só no E2E.
- **Credencial:** `{"username", "password"}` (Basic) ou `{"client_id", "client_secret"}` com
  `token_url` (OAuth client credentials), no Vault como as outras.
- **Consulta:** `GET <service_url>/<entity>?$filter=<field> eq '<valor>'&$top=1`, com os nomes
  no padrão de identificador e o valor com as aspas dobradas (sintaxe OData).
"""

import asyncio
import ipaddress
import json
import os
import re
import socket
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any, ClassVar
from urllib.parse import quote, urlparse

import httpcore
import httpx

from aid_connectors.base import (
    Batch,
    Checkpoint,
    ConfigErrors,
    ConnectorError,
    LookupQuery,
    LookupResult,
    RateLimitPolicy,
    Secret,
    TestResult,
)
from aid_connectors.common import is_loopback

IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
SERVICE_PATH = re.compile(r"^/[A-Za-z0-9_./;=-]{1,200}$")
MAX_VALUE = 255

Resolver = Callable[[str], Awaitable[Sequence[str]]]


async def resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def all_public(addresses: Sequence[str]) -> bool:
    return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)


class PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """Rede do transporte: resolve o host, recusa se algum endereço não for público e conecta no
    endereço conferido. O TLS recebe o nome original (SNI e verificação do certificado)."""

    def __init__(self, resolver: Resolver) -> None:
        self.resolver = resolver
        self.inner = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = list(await self.resolver(host))
        except OSError as exc:
            raise httpcore.ConnectError(f"nome não resolveu: {host}") from exc
        if not all_public(addresses):
            raise httpcore.ConnectError("endereço não público")
        return await self.inner.connect_tcp(
            addresses[0], port, timeout, local_address, socket_options
        )

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Any = None
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("socket local não é permitido")

    async def sleep(self, seconds: float) -> None:
        await self.inner.sleep(seconds)


def public_transport(resolver: Resolver = resolve) -> httpx.AsyncHTTPTransport:
    """O transporte padrão do httpx com a rede trocada pela que só conecta em endereço público.
    O pool é recriado com a mesma configuração de TLS do httpx (verificação ligada)."""
    transport = httpx.AsyncHTTPTransport()
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=httpx.create_ssl_context(),
        network_backend=PublicOnlyBackend(resolver),
    )
    return transport


def loopback_allowed(environ: Mapping[str, str] = os.environ) -> bool:
    return environ.get("AID_ODATA_ALLOW_LOOPBACK") == "1"


def shape_ok(url: str) -> bool:
    """HTTPS, host por nome, sem usuário, porta padrão; o resto é conferido na resolução."""
    if is_loopback(url):
        return loopback_allowed()
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    host = parsed.hostname or ""
    try:
        ipaddress.ip_address(host)
        literal = True
    except ValueError:
        literal = False
    return (
        parsed.scheme == "https"
        and bool(host)
        and not literal
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
        and not parsed.query
        and not parsed.fragment
        and SERVICE_PATH.match(parsed.path or "/x") is not None
    )


def literal(value: str) -> str:
    if any(char in value for char in "\r\n\x00") or not 0 < len(value) <= MAX_VALUE:
        raise ConnectorError("invalid", "Valor de consulta inválido.")
    return "'" + value.replace("'", "''") + "'"


def records(body: Any) -> list[Mapping[str, Any]]:
    """v2: `{"d": {"results": [...]}}`; v4: `{"value": [...]}`."""
    if not isinstance(body, Mapping):
        return []
    found = body.get("value")
    if found is None and isinstance(body.get("d"), Mapping):
        found = body["d"].get("results")
    return [item for item in found or [] if isinstance(item, Mapping)]


class ODataConnector:
    provider: ClassVar[str] = "odata"
    rate_limit: ClassVar[RateLimitPolicy] = RateLimitPolicy(requests_per_minute=60)
    # Só consulta: o agendador não pede Sincronização para este provedor.
    collects: ClassVar[bool] = False

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = resolve,
    ) -> None:
        self.transport = transport
        self.resolver = resolver
        self.token: tuple[str, float] | None = None

    def validate_config(self, config: Mapping[str, Any]) -> ConfigErrors:
        errors: ConfigErrors = {}
        if not shape_ok(str(config.get("service_url", ""))):
            errors["service_url"] = "URL HTTPS do serviço OData, com nome de host e sem usuário"
        if config.get("version", "v2") not in ("v2", "v4"):
            errors["version"] = "v2 ou v4"
        auth = config.get("auth", "basic")
        if auth not in ("basic", "oauth_client_credentials"):
            errors["auth"] = "basic ou oauth_client_credentials"
        if auth == "oauth_client_credentials" and not shape_ok(str(config.get("token_url", ""))):
            errors["token_url"] = "URL HTTPS do token, com nome de host e sem usuário"  # noqa: S105
        rpm = config.get("requests_per_minute", 60)
        if not isinstance(rpm, int) or not 1 <= rpm <= 600:
            errors["requests_per_minute"] = "de 1 a 600"
        return errors

    async def public(self, url: str) -> None:
        """O host resolve só para endereços públicos agora (um nome não aponta para a rede
        interna da plataforma)."""
        if is_loopback(url) and loopback_allowed():
            return
        if not shape_ok(url):
            raise ConnectorError("invalid", "Endereço do serviço OData recusado.")
        try:
            addresses = await self.resolver(urlparse(url).hostname or "")
        except OSError as exc:
            raise ConnectorError("transient", "O nome do serviço OData não resolveu.") from exc
        if not all_public(addresses):
            raise ConnectorError("invalid", "O serviço OData resolve para endereço não público.")

    def credential(self, secret: Secret, auth: str) -> Mapping[str, str]:
        try:
            found = json.loads(secret.reveal())
        except ValueError:
            found = None
        needed = {"username", "password"} if auth == "basic" else {"client_id", "client_secret"}
        if not isinstance(found, dict) or not needed <= found.keys():
            raise ConnectorError("auth", f"A credencial precisa de {' e '.join(sorted(needed))}.")
        return {key: str(found[key]) for key in needed}

    async def headers(
        self, client: httpx.AsyncClient, secret: Secret, config: Mapping[str, Any]
    ) -> dict[str, str]:
        auth = str(config.get("auth", "basic"))
        found = self.credential(secret, auth)
        if auth == "basic":
            basic = httpx.BasicAuth(found["username"], found["password"])
            request = next(basic.auth_flow(httpx.Request("GET", "https://x")))
            return {"authorization": request.headers["authorization"]}
        if self.token is None or self.token[1] < time.monotonic() + 60:
            url = str(config["token_url"])
            await self.public(url)
            try:
                response = await client.post(
                    url,
                    data={"grant_type": "client_credentials"},
                    auth=(found["client_id"], found["client_secret"]),
                )
                body = response.json() if response.status_code == 200 else {}
            except (httpx.HTTPError, ValueError) as exc:
                raise ConnectorError("transient", "O servidor de token não respondeu.") from exc
            if response.status_code in (400, 401):
                raise ConnectorError("auth", "O servidor de token recusou a credencial.")
            if "access_token" not in body:
                raise ConnectorError("transient", "Resposta inesperada do servidor de token.")
            self.token = (
                str(body["access_token"]),
                time.monotonic() + float(body.get("expires_in", 600)),
            )
        return {"authorization": f"Bearer {self.token[0]}"}

    def network(self, url: str) -> httpx.AsyncBaseTransport | None:
        if self.transport is not None:
            return self.transport
        if is_loopback(url) and loopback_allowed():
            return None
        return public_transport(self.resolver)

    async def get(self, secret: Secret, config: Mapping[str, Any], url: str) -> httpx.Response:
        await self.public(str(config["service_url"]))
        async with httpx.AsyncClient(
            transport=self.network(url), timeout=httpx.Timeout(20.0), follow_redirects=False
        ) as client:
            headers = await self.headers(client, secret, config)
            try:
                response = await client.get(url, headers={**headers, "accept": "application/json"})
            except httpx.HTTPError as exc:
                raise ConnectorError(
                    "transient",
                    "O serviço OData não respondeu (ou resolveu para endereço não público).",
                ) from exc
        if response.status_code in (401, 403):
            raise ConnectorError("auth", "O serviço OData recusou a credencial.")
        if response.status_code == 404:
            raise ConnectorError("invalid", "Entidade não encontrada no serviço OData.")
        if response.status_code == 400:
            raise ConnectorError("invalid", "O serviço OData recusou a consulta (campo ou filtro).")
        if response.status_code != 200:
            raise ConnectorError(
                "transient", f"O serviço OData respondeu HTTP {response.status_code}."
            )
        return response

    async def test_connection(
        self, secret: Secret, config: Mapping[str, Any], *, preview: bool = False
    ) -> TestResult:
        try:
            await self.get(secret, config, str(config["service_url"]).rstrip("/") + "/$metadata")
        except ConnectorError as exc:
            return TestResult(False, exc.message)
        return TestResult(True, "Conexão estabelecida com o serviço OData.")

    async def lookup(
        self, secret: Secret, config: Mapping[str, Any], query: LookupQuery
    ) -> LookupResult:
        extra = [name for name in (query.status_field, query.id_field) if name]
        names = [query.entity, query.field, *extra]
        if not all(IDENTIFIER.match(name) for name in names):
            raise ConnectorError("invalid", "Consulta recusada: entidade ou campo fora do padrão.")
        selected = ",".join(dict.fromkeys([query.field, *extra]))
        params = [
            f"$filter={quote(f'{query.field} eq {literal(query.value)}', safe='')}",
            "$top=1",
            f"$select={selected}",
        ]
        if config.get("version", "v2") == "v2":
            params.append("$format=json")
        base = str(config["service_url"]).rstrip("/")
        response = await self.get(secret, config, f"{base}/{query.entity}?{'&'.join(params)}")
        try:
            found = records(response.json())
        except ValueError as exc:
            raise ConnectorError("transient", "Resposta inesperada do serviço OData.") from exc
        if not found:
            return LookupResult(False)
        record = found[0]
        status = record.get(query.status_field) if query.status_field else None
        # A chave do registro no destino (ex.: SalesOrder), não o valor consultado.
        key = record.get(query.id_field) if query.id_field else None
        return LookupResult(True, str(key) if key else None, str(status) if status else None)

    async def collect(
        self, secret: Secret, config: Mapping[str, Any], checkpoint: Checkpoint | None
    ) -> AsyncIterator[Batch]:
        # Só consulta: nunca há Eventos a coletar.
        return
        yield  # pragma: no cover
