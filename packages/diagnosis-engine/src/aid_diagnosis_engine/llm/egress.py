"""Para onde as chamadas de IA vão (ADR-0018): cada pedido HTTP de um provedor registra o log
`ai.egress` com o provedor, o host e a região, sem conteúdo. Os provedores do Brasil só aceitam
hosts do Brasil (e o servidor de metadados do GCP): outro host é recusado antes de sair. A
verificação diária usa `recording()` para saber os hosts que uma chamada realmente usou."""

import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

from aid_diagnosis_engine.llm.base import LLMUnavailableError

log = logging.getLogger("aid.ai.egress")
BR_REGION = "southamerica-east1"
METADATA_HOST = "metadata.google.internal"
US_HOSTS = {"api.anthropic.com", "api.voyageai.com"}
_recorded: ContextVar[list[str] | None] = ContextVar("ai_egress", default=None)


def region_of(host: str) -> str:
    if host.startswith(f"{BR_REGION}-") or host.endswith(f".{BR_REGION}.rep.googleapis.com"):
        return BR_REGION
    if host == METADATA_HOST:
        return "local"
    if host in US_HOSTS:
        return "us"
    return "unknown"


def record(provider: str, host: str) -> None:
    found = _recorded.get()
    if found is not None:
        found.append(host)
    log.info(
        "ai.egress",
        extra={"fields": {"provider": provider, "host": host, "region": region_of(host)}},
    )


@contextmanager
def recording() -> Iterator[list[str]]:
    """Os hosts que as chamadas de IA deste bloco usaram."""
    hosts: list[str] = []
    token = _recorded.set(hosts)
    try:
        yield hosts
    finally:
        _recorded.reset(token)


def hook(
    provider: str, allowed: set[str] | None = None
) -> Callable[[httpx.Request], Awaitable[None]]:
    """Gancho de pedido do httpx: registra o egress e, com `allowed`, recusa outro host."""

    async def on_request(request: httpx.Request) -> None:
        host = request.url.host
        if allowed is not None and host not in allowed:
            log.error(
                "ai.egress_blocked",
                extra={"fields": {"provider": provider, "host": host, "region": region_of(host)}},
            )
            raise LLMUnavailableError(f"O provedor {provider} não fala com {host}.")
        record(provider, host)

    return on_request
