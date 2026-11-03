"""Claude pela API da Anthropic (provedor padrão, ADR-0007), com embeddings da Voyage.

Saída estruturada por `messages.parse` com o schema Pydantic (structured outputs): o Sonnet 5.5
e o Haiku 5.5 recusam `tool_choice` forçado, e o formato de saída garante JSON no schema sem
precisar de ferramenta. Nenhuma ferramenta com efeito é declarada. O bloco de sistema (as
guardas e as instruções, estáveis) vai com cache de prompt. Os retries ficam com o GuardedLLM:
o SDK não repete sozinho.
"""

import time
from collections.abc import Sequence
from typing import Any, cast

import anthropic
from anthropic.types import MessageParam
from pydantic import BaseModel, ValidationError

from aid_diagnosis_engine.llm.base import (
    InputType,
    LLMInvalidOutputError,
    LLMTransientError,
    LLMUnavailableError,
    Msg,
    StructuredResult,
    Tier,
    Usage,
    describe_validation,
)
from aid_diagnosis_engine.llm.voyage import VoyageEmbeddings

MODELS: dict[Tier, str] = {"reasoning": "claude-sonnet-5-5", "fast": "claude-haiku-5-5"}
TRANSIENT = (
    anthropic.RateLimitError,
    anthropic.OverloadedError,
    anthropic.ServiceUnavailableError,
    anthropic.DeadlineExceededError,
    anthropic.InternalServerError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
)
UNAVAILABLE = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
    anthropic.BadRequestError,
)


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        embeddings: VoyageEmbeddings | None = None,
    ) -> None:
        self.client = client or anthropic.AsyncAnthropic(max_retries=0)
        self.embeddings = embeddings or VoyageEmbeddings()

    @property
    def embedding_dimensions(self) -> int:
        return self.embeddings.dimensions

    async def complete_structured(
        self,
        *,
        system: str,
        messages: Sequence[Msg],
        schema: type[Any],
        model_tier: Tier,
        max_tokens: int,
    ) -> StructuredResult[Any]:
        model = MODELS[model_tier]
        start = time.monotonic()
        try:
            response = await self.client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[
                    cast(MessageParam, {"role": m.role, "content": m.content}) for m in messages
                ],
                output_format=schema,
            )
        except TRANSIENT as exc:
            raise LLMTransientError(f"Anthropic: {type(exc).__name__}") from exc
        except UNAVAILABLE as exc:
            raise LLMUnavailableError(f"Anthropic: {type(exc).__name__}") from exc
        except ValidationError as exc:
            raise LLMInvalidOutputError(describe_validation(exc)) from exc
        except (anthropic.AnthropicError, TypeError) as exc:
            # 413, 409, 422, resposta inesperada ou credencial ausente (o SDK levanta TypeError
            # sem chave): nada que uma nova tentativa resolva.
            raise LLMUnavailableError(f"Anthropic: {type(exc).__name__}") from exc
        usage = Usage(
            provider=self.name,
            model=model,
            input_tokens=response.usage.input_tokens
            + (response.usage.cache_read_input_tokens or 0)
            + (response.usage.cache_creation_input_tokens or 0),
            output_tokens=response.usage.output_tokens,
            latency_ms=round((time.monotonic() - start) * 1000),
        )
        if response.stop_reason == "refusal":
            # Sem fallback para outro modelo: o diagnóstico cai no modo degradado (só Regras).
            raise LLMUnavailableError("O modelo recusou a análise.", usage)
        if response.stop_reason == "max_tokens":
            raise LLMInvalidOutputError("resposta cortada pelo limite de tokens", usage)
        output = response.parsed_output
        if not isinstance(output, BaseModel):
            raise LLMInvalidOutputError("resposta sem o objeto do schema", usage)
        return StructuredResult(output, usage)

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        return await self.embeddings.embed(texts, input_type=input_type)
