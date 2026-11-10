"""Provedor por Organização (`tenants.llm_provider`, derivado do perfil de IA `ai_profile`,
ADR-0018): trocar é mudar a coluna, sem deploy. As credenciais vêm do Secret Manager pelo
ambiente do worker (ANTHROPIC_API_KEY, VOYAGE_API_KEY, GCP_PROJECT_ID). O dedicado usa o projeto
da Organização (`ai_project`) quando é o do cliente."""

from collections.abc import Callable
from functools import cache

from aid_diagnosis_engine.llm.anthropic_provider import AnthropicProvider
from aid_diagnosis_engine.llm.base import LLMProvider, LLMUnavailableError
from aid_diagnosis_engine.llm.vertex import EMBEDDING_MODEL, VertexProvider
from aid_diagnosis_engine.llm.voyage import MODEL as VOYAGE_MODEL

PROVIDERS: dict[str, Callable[[str | None], LLMProvider]] = {
    "anthropic": lambda _project: AnthropicProvider(),
    "vertex": lambda _project: VertexProvider(),
    "vertex_dedicated": lambda project: VertexProvider(project=project, dedicated=True),
}
# Perfil de IA → provedor.
PROFILES = {"standard": "anthropic", "br_region": "vertex", "dedicated": "vertex_dedicated"}
# Índices de embedding que cada perfil pode consultar: o Brasil nunca manda a pergunta ao Voyage.
INDEXES: dict[str, frozenset[str]] = {
    "standard": frozenset({VOYAGE_MODEL, EMBEDDING_MODEL}),
    "br_region": frozenset({EMBEDDING_MODEL}),
    "dedicated": frozenset({EMBEDDING_MODEL}),
}
# Modelo de embedding de cada provedor (o índice para onde o reindex leva os documentos).
EMBEDDING_MODELS = {
    "anthropic": VOYAGE_MODEL,
    "vertex": EMBEDDING_MODEL,
    "vertex_dedicated": EMBEDDING_MODEL,
}
# Quem gera o embedding de cada índice (o do Vertex é sempre o compartilhado no Brasil).
INDEX_PROVIDERS = {VOYAGE_MODEL: "anthropic", EMBEDDING_MODEL: "vertex"}


@cache
def provider_for(name: str, project: str | None = None) -> LLMProvider:
    """Uma instância por provedor (e projeto) e processo: o cliente HTTP e o token são
    reaproveitados."""
    factory = PROVIDERS.get(name)
    if factory is None:
        raise LLMUnavailableError(f"Provedor de IA desconhecido: {name}.")
    return factory(project if name == "vertex_dedicated" else None)
