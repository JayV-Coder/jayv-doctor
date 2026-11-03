"""Provedor por Organização (`tenants.llm_provider`): trocar é mudar a coluna, sem deploy. As
credenciais vêm do Secret Manager pelo ambiente do worker (ANTHROPIC_API_KEY, VOYAGE_API_KEY,
GCP_PROJECT_ID)."""

from collections.abc import Callable
from functools import cache

from aid_diagnosis_engine.llm.anthropic_provider import AnthropicProvider
from aid_diagnosis_engine.llm.base import LLMProvider, LLMUnavailableError
from aid_diagnosis_engine.llm.vertex import VertexProvider

PROVIDERS: dict[str, Callable[[], LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "vertex": VertexProvider,
}


@cache
def provider_for(name: str) -> LLMProvider:
    """Uma instância por provedor e processo (o cliente HTTP e o token são reaproveitados)."""
    factory = PROVIDERS.get(name)
    if factory is None:
        raise LLMUnavailableError(f"Provedor de IA desconhecido: {name}.")
    return factory()
