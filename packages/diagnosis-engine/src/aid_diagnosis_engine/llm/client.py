"""O caminho único até o LLM: guardas, orçamento de entrada, cache, retry, circuit breaker,
validação (com 1 nova tentativa mostrando o erro) e registro de uso. O diagnóstico (#24) usa só
isto; nenhum ponto do código chama um provedor direto."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from aid_diagnosis_engine.llm.base import (
    LLMInvalidOutputError,
    LLMProvider,
    Msg,
    StructuredResult,
    Tier,
    Usage,
)
from aid_diagnosis_engine.llm.cache import ResponseCache, cache_key
from aid_diagnosis_engine.llm.guards import GUARD, Untrusted, render, within_budget
from aid_diagnosis_engine.llm.resilience import CircuitBreaker, RetryPolicy, resilient

INPUT_BUDGET = 60_000
UsageSink = Callable[[Usage], Awaitable[None]]


@dataclass
class GuardedLLM:
    provider: LLMProvider
    cache: ResponseCache | None = None
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    usage_sink: UsageSink | None = None
    input_budget: int = INPUT_BUDGET

    async def structured[M: BaseModel](
        self,
        *,
        system: str,
        instructions: str,
        untrusted: Sequence[Untrusted],
        schema: type[M],
        tier: Tier,
        max_tokens: int = 4096,
        check: Callable[[M], str | None] | None = None,
    ) -> StructuredResult[M]:
        """`check` valida o que o schema não alcança (ex.: toda Evidência citada existe); a
        recusa dele conta como saída inválida, com a mesma nova tentativa."""
        items = within_budget(untrusted, self.input_budget)
        guarded_system = f"{GUARD}\n\n{system}"
        # O nonce muda a cada chamada; a chave do cache usa o conteúdo, não o texto montado.
        key_messages = [Msg("user", instructions)] + [
            Msg("user", f"{item.kind}:{item.ref}:{item.content}") for item in items
        ]
        key = cache_key(
            self.provider.name, tier, guarded_system, key_messages, schema.model_json_schema()
        )
        if self.cache is not None and (hit := await self.cache.get(key)) is not None:
            output = schema.model_validate_json(hit)
            usage = Usage(self.provider.name, tier, 0, 0, 0, cached=True)
            await self._record(usage)
            return StructuredResult(output, usage)

        data, _ = render(items)
        messages = [Msg("user", f"{instructions}\n\n{data}")]
        problem: str | None = None
        for _attempt in range(2):
            attempt_messages = messages
            if problem is not None:
                attempt_messages = [
                    *messages,
                    Msg(
                        "user",
                        "A resposta anterior foi recusada pela validação: "
                        f"{problem}. Responda de novo seguindo o schema e citando só "
                        "Evidências fornecidas.",
                    ),
                ]

            async def call(current: list[Msg] = attempt_messages) -> StructuredResult[M]:
                return await self.provider.complete_structured(
                    system=guarded_system,
                    messages=current,
                    schema=schema,
                    model_tier=tier,
                    max_tokens=max_tokens,
                )

            try:
                result = await resilient(call, self.policy, self.breaker)
            except LLMInvalidOutputError as exc:
                problem = str(exc)
                continue
            await self._record(result.usage)
            problem = check(result.output) if check else None
            if problem is None:
                if self.cache is not None:
                    await self.cache.put(key, result.output.model_dump_json())
                return result
        raise LLMInvalidOutputError(f"Saída do modelo fora do schema duas vezes: {problem}")

    async def _record(self, usage: Usage) -> None:
        if self.usage_sink is not None:
            await self.usage_sink(usage)


def validate_output[M: BaseModel](schema: type[M], text: str) -> M:
    """Para os provedores que devolvem texto: erro de validação vira `LLMInvalidOutputError` com a
    mensagem do Pydantic, sem ecoar o conteúdo."""
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        fields = "; ".join(
            f"{'.'.join(str(p) for p in error['loc'])}: {error['msg']}" for error in exc.errors()
        )
        raise LLMInvalidOutputError(fields or "JSON inválido") from exc
