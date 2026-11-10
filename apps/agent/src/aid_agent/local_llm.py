"""Modelo local (ticket #46, ADR-0019): o agente busca na plataforma os pedidos (prompt já
sanitizado), chama o servidor compatível com a API da OpenAI da rede do cliente (vLLM, TGI) e
devolve só a resposta. Continua só de saída: o long-poll é para a plataforma, e a chamada ao
modelo fica na rede do cliente. Só os campos de um chat completion seguem para o servidor."""

import logging
import threading
from collections.abc import Callable
from typing import Any

import httpx

from aid_agent.client import LocalModel, PlatformError

log = logging.getLogger(__name__)
FIELDS = {"model", "messages", "response_format", "max_tokens", "temperature"}
Post = Callable[..., httpx.Response]


def handle(local: LocalModel, found: dict[str, Any], llm: dict[str, Any], post: Post) -> bool:
    """Um pedido: chama o servidor local e devolve a resposta ou o erro (sem o corpo)."""
    body = {key: value for key, value in dict(found.get("request") or {}).items() if key in FIELDS}
    try:
        response = post(
            f"{llm['base_url']}/chat/completions",
            json=body,
            # O prazo do pedido, o mesmo que o worker espera.
            timeout=float(found.get("timeout_seconds") or 120),
        )
        response.raise_for_status()
        result: dict[str, Any] = {"response": response.json()}
    except httpx.HTTPStatusError as exc:
        result = {"error": f"o servidor local respondeu HTTP {exc.response.status_code}"}
    except (httpx.HTTPError, ValueError) as exc:
        result = {"error": f"o servidor local não respondeu ({type(exc).__name__})"}
    local.answer(str(found["id"]), result)
    return "response" in result


def serve(
    local: LocalModel,
    current: Callable[[], dict[str, Any] | None],
    stop: threading.Event,
    post: Post = httpx.post,
) -> None:
    """Laço da thread do modelo local: só roda com `llm` na config da plataforma."""
    while not stop.is_set():
        llm = current()
        if not llm:
            stop.wait(30)
            continue
        try:
            found = local.next()
            if found is not None:
                handle(local, found, llm, post)
        except PlatformError:
            log.error("a plataforma recusou o agente no modelo local: confira se ele foi revogado")
            stop.wait(60)
        except httpx.HTTPError:
            log.warning("sem rede com a plataforma para o modelo local")
            stop.wait(10)
        except Exception:
            # Resposta inesperada (ex.: proxy devolvendo HTML): a thread não morre por isso.
            log.exception("falha no modelo local; tentando de novo")
            stop.wait(10)
