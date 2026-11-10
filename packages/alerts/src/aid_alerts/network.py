"""Saída HTTP para endereços do cliente (webhooks, #42) sem alcançar a rede da plataforma.

- No cadastro, `check_url`: HTTPS, sem usuário na URL, e o host (por nome ou IP) só com
  endereços públicos. Nomes de rede interna (`localhost`, `*.internal`, `metadata…`) nem resolvem.
- Na entrega, `public_transport`: a conexão resolve o nome, confere de novo e conecta no
  endereço conferido (o TLS valida o nome original). Um DNS que muda de resposta entre o
  cadastro e a entrega (rebinding) não leva a `169.254.169.254` nem à VPC.
"""

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from urllib.parse import urlparse

import httpcore
import httpx

Resolver = Callable[[str], Awaitable[Sequence[str]]]
INTERNAL_NAMES = re.compile(
    r"(^|\.)(localhost|internal|local|lan|home\.arpa|intranet|corp)$|^metadata(\.|$)",
    re.IGNORECASE,
)


class UnsafeUrlError(ValueError):
    """Endereço recusado; a mensagem diz a regra, sem ecoar o endereço."""


async def resolve(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def all_public(addresses: Sequence[str]) -> bool:
    return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)


def shape(url: str) -> str:
    """O host, se a forma da URL é aceitável; senão `UnsafeUrlError`."""
    try:
        parsed = urlparse(url)
        parsed.port  # noqa: B018 - porta inválida levanta ValueError
    except ValueError as exc:
        raise UnsafeUrlError("URL inválida") from exc
    host = (parsed.hostname or "").rstrip(".")
    if parsed.scheme != "https":
        raise UnsafeUrlError("só HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("sem usuário e senha na URL")
    if not host or len(url) > 1000:
        raise UnsafeUrlError("URL sem host ou longa demais")
    if INTERNAL_NAMES.search(host):
        raise UnsafeUrlError("host de rede interna ou de metadados")
    return host


async def check_url(url: str, resolver: Resolver = resolve) -> None:
    host = shape(url)
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise UnsafeUrlError("IP privado, local ou de metadados")
        return
    try:
        addresses = list(await resolver(host))
    except OSError as exc:
        raise UnsafeUrlError("o nome do host não resolve") from exc
    if not all_public(addresses):
        raise UnsafeUrlError("o host resolve para IP privado, local ou de metadados")


class PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, resolver: Resolver = resolve) -> None:
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
            literal = ipaddress.ip_address(host.strip("[]"))
            addresses = [str(literal)]
        except ValueError:
            try:
                addresses = list(await self.resolver(host))
            except OSError as exc:
                raise httpcore.ConnectError("nome não resolveu") from exc
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
    """O transporte padrão do httpx com a rede trocada pela que só conecta em endereço público,
    com a verificação de TLS do httpx."""
    transport = httpx.AsyncHTTPTransport()
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=httpx.create_ssl_context(),
        network_backend=PublicOnlyBackend(resolver),
    )
    return transport
