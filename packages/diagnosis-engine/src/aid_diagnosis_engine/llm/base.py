"""Interface do provedor de LLM (ADR-0007). O motor de diagnóstico só conhece este Protocol: a
Organização escolhe o provedor (`tenants.llm_provider`) sem deploy."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

Tier = Literal["reasoning", "fast"]
InputType = Literal["document", "query"]
T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Msg:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Usage:
    """Vai para `usage_records` (#31): quem pagou o quê, sem conteúdo."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cached: bool = False


@dataclass(frozen=True)
class StructuredResult[M: BaseModel]:
    output: M
    usage: Usage


class LLMError(Exception):
    """Falha do provedor que o diagnóstico trata como modo degradado (as Regras continuam).
    `usage`: o que o provedor cobrou mesmo assim (recusa, saída cortada ou fora do schema)."""

    def __init__(self, message: str, usage: Usage | None = None) -> None:
        super().__init__(message)
        self.usage = usage


class LLMTransientError(LLMError):
    """429, 5xx, timeout, rede: vale tentar de novo."""


class LLMUnavailableError(LLMError):
    """Circuito aberto, credencial ausente ou recusa: não adianta tentar agora."""


class LLMInvalidOutputError(LLMError):
    """A saída não passou no schema duas vezes: o diagnóstico fica `failed_llm`."""


class LLMProvider(Protocol):
    name: str

    async def complete_structured(
        self,
        *,
        system: str,
        messages: Sequence[Msg],
        schema: type[T],
        model_tier: Tier,
        max_tokens: int,
    ) -> StructuredResult[T]:
        """Uma resposta no formato de `schema`, já validada pelo Pydantic. Levanta
        `LLMTransientError` (repetível), `LLMUnavailableError` ou `LLMInvalidOutputError`."""
        ...

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]: ...

    @property
    def embedding_dimensions(self) -> int:
        """Registrada junto com cada vetor: trocar de provedor exige reindexar."""
        ...

    @property
    def embedding_model(self) -> str:
        """Gravado com cada Fragmento: a busca só compara vetores do mesmo modelo."""
        ...


def describe_validation(exc: ValidationError) -> str:
    """Só os campos e as regras: o valor pode trazer dado do cliente."""
    return (
        "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        or "JSON inválido"
    )
