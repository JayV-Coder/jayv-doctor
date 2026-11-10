"""Modelo local no ambiente do cliente (perfil `local`, ticket #46, ADR-0019): um servidor
compatível com a API da OpenAI (vLLM, TGI) na rede do cliente. Só o prompt (Evidências já
sanitizadas) vai, e só a resposta estruturada volta. O caminho até lá é um `LocalTransport`: o
agente local (pela fila do banco, no worker) ou um endpoint privado (Private Service Connect).

Sem embeddings locais: a Base de conhecimento desse perfil busca só pelo texto. Indisponível, o
provedor levanta `LLMUnavailableError` e o Diagnóstico sai em `rules_only`; nada cai num
provedor em nuvem."""

import time
from collections.abc import Sequence
from typing import Any, Protocol

import httpx

from aid_diagnosis_engine.llm import egress
from aid_diagnosis_engine.llm.base import (
    InputType,
    LLMInvalidOutputError,
    LLMTransientError,
    LLMUnavailableError,
    Msg,
    StructuredResult,
    Tier,
    Usage,
)
from aid_diagnosis_engine.llm.client import validate_output


class LocalTransport(Protocol):
    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        """A resposta de `POST /v1/chat/completions` do servidor do cliente."""
        ...


class PrivateEndpoint:
    """Endpoint privado do servidor do cliente (Private Service Connect): só esse host."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        host = httpx.URL(self.base_url).host
        self.client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            event_hooks={"request": [egress.hook("local", {host})]},
        )

    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self.client.post(f"{self.base_url}/chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise LLMUnavailableError("O modelo local não respondeu.") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise LLMTransientError(f"O modelo local respondeu HTTP {response.status_code}.")
        if response.status_code != 200:
            raise LLMUnavailableError(
                f"O modelo local recusou o pedido (HTTP {response.status_code})."
            )
        found: dict[str, Any] = response.json()
        return found


class LocalProvider:
    name = "local"
    # Sem embeddings locais: nenhum índice vetorial para este perfil.
    embedding_model = "local-text-only"
    embedding_dimensions = 0

    def __init__(self, transport: LocalTransport, model: str) -> None:
        self.transport = transport
        self.model = model

    async def complete_structured(
        self,
        *,
        system: str,
        messages: Sequence[Msg],
        schema: type[Any],
        model_tier: Tier,
        max_tokens: int,
    ) -> StructuredResult[Any]:
        start = time.monotonic()
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                *({"role": m.role, "content": m.content} for m in messages),
            ],
            # Saída guiada pelo schema (vLLM e TGI aceitam `json_schema`).
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
            },
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        found = await self.transport.chat(body)
        metadata = found.get("usage") or {}
        usage = Usage(
            provider=self.name,
            model=self.model,
            input_tokens=int(metadata.get("prompt_tokens", 0)),
            output_tokens=int(metadata.get("completion_tokens", 0)),
            latency_ms=round((time.monotonic() - start) * 1000),
        )
        choices = found.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise LLMUnavailableError("O modelo local não devolveu resposta.", usage)
        first = choices[0]
        if first.get("finish_reason") == "length":
            raise LLMInvalidOutputError("resposta cortada pelo limite de tokens", usage)
        text = str((first.get("message") or {}).get("content") or "")
        return StructuredResult(validate_output(schema, text, usage), usage)

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        raise LLMUnavailableError("O perfil local não gera embeddings: a busca é pelo texto.")
