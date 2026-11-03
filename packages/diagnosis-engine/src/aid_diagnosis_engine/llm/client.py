"""O caminho único até o LLM: guardas, orçamento de entrada, cache, retry, circuit breaker,
validação (com 1 nova tentativa mostrando o erro) e registro de uso. O diagnóstico (#24) usa só
isto; nenhum ponto do código chama um provedor direto."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from aid_diagnosis_engine.llm.base import (
    LLMError,
    LLMInvalidOutputError,
    LLMProvider,
    Msg,
    StructuredResult,
    Tier,
    Usage,
    describe_validation,
)
from aid_diagnosis_engine.llm.cache import ResponseCache, cache_key
from aid_diagnosis_engine.llm.guards import (
    GUARD,
    Untrusted,
    estimate_tokens,
    render,
    within_budget,
)
from aid_diagnosis_engine.llm.resilience import (
    CircuitBreaker,
    RetryPolicy,
    breaker_for,
    resilient,
)

INPUT_BUDGET = 60_000
UsageSink = Callable[[Usage], Awaitable[None]]


@dataclass
class GuardedLLM:
    provider: LLMProvider
    cache: ResponseCache | None = None
    # Por padrão, o breaker do provedor no processo: todos os diagnósticos somam as falhas.
    breaker: CircuitBreaker | None = None
    policy: RetryPolicy = field(default_factory=RetryPolicy)
    usage_sink: UsageSink | None = None
    input_budget: int = INPUT_BUDGET

    def __post_init__(self) -> None:
        if self.breaker is None:
            self.breaker = breaker_for(self.provider.name)

    async def structured[M: BaseModel](
        self,
        *,
        scope: str,
        system: str,
        instructions: str,
        untrusted: Sequence[Untrusted],
        schema: type[M],
        tier: Tier,
        max_tokens: int = 4096,
        check: Callable[[M], str | None] | None = None,
    ) -> StructuredResult[M]:
        """`scope` é a Organização (entra na chave do cache). `check` valida o que o schema não
        alcança (ex.: toda Evidência citada existe); a recusa dele conta como saída inválida,
        com a mesma nova tentativa, e vale também para a resposta vinda do cache."""
        guarded_system = f"{GUARD}\n\n{system}"
        # O orçamento conta também o sistema e as instruções, não só os dados.
        fixed = estimate_tokens(guarded_system) + estimate_tokens(instructions)
        items = within_budget(untrusted, max(self.input_budget - fixed, 0))
        # O nonce muda a cada chamada; a chave usa o conteúdo, campo a campo, sem ambiguidade.
        key = cache_key(
            scope,
            self.provider.name,
            tier,
            guarded_system,
            [[instructions], *([item.kind, item.ref, item.content] for item in items)],
            schema.model_json_schema(),
        )
        if self.cache is not None and (hit := await self.cache.get(key)) is not None:
            try:
                cached = schema.model_validate_json(hit)
            except ValidationError:
                cached = None
            if cached is not None and (check is None or check(cached) is None):
                usage = Usage(self.provider.name, tier, 0, 0, 0, cached=True)
                await self._record(usage)
                return StructuredResult(cached, usage)

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

            breaker = self.breaker or breaker_for(self.provider.name)
            try:
                result = await resilient(call, self.policy, breaker)
            except LLMInvalidOutputError as exc:
                # Saída cortada ou fora do schema também foi cobrada.
                await self._record(exc.usage)
                problem = str(exc)
                continue
            except LLMError as exc:
                await self._record(exc.usage)
                raise
            await self._record(result.usage)
            problem = check(result.output) if check else None
            if problem is None:
                if self.cache is not None:
                    await self.cache.put(key, result.output.model_dump_json())
                return result
        raise LLMInvalidOutputError(f"Saída do modelo fora do schema duas vezes: {problem}")

    async def _record(self, usage: Usage | None) -> None:
        if self.usage_sink is not None and usage is not None:
            await self.usage_sink(usage)


def validate_output[M: BaseModel](schema: type[M], text: str, usage: Usage | None = None) -> M:
    """Para os provedores que devolvem texto: erro de validação vira `LLMInvalidOutputError`
    com os campos e as regras, sem ecoar o conteúdo."""
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        raise LLMInvalidOutputError(describe_validation(exc), usage) from exc
