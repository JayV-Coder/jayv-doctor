"""Provedor por Organização (`tenants.llm_provider`, derivado do perfil de IA `ai_profile`,
ADR-0018): trocar é mudar o perfil (`doctor.set_ai_profile`), sem deploy; o banco mantém o
provedor e o perfil juntos. As credenciais vêm do Secret Manager pelo
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
PROFILES = {
    "standard": "anthropic",
    "br_region": "vertex",
    "dedicated": "vertex_dedicated",
    # O local depende da configuração da Organização (agente ou endpoint privado): quem monta é
    # o worker, nunca este registro (ADR-0019).
    "local": "local",
}
# Índices de embedding que cada perfil pode consultar: o Brasil nunca manda a pergunta ao Voyage.
INDEXES: dict[str, frozenset[str]] = {
    "standard": frozenset({VOYAGE_MODEL, EMBEDDING_MODEL}),
    "br_region": frozenset({EMBEDDING_MODEL}),
    "dedicated": frozenset({EMBEDDING_MODEL}),
    # Sem embeddings: só o texto. Nem o índice antigo (a pergunta não sai da rede do cliente).
    "local": frozenset(),
}
# Modelo de embedding de cada provedor (o índice para onde o reindex leva os documentos).
EMBEDDING_MODELS: dict[str, str | None] = {
    "anthropic": VOYAGE_MODEL,
    "vertex": EMBEDDING_MODEL,
    "vertex_dedicated": EMBEDDING_MODEL,
    # Sem índice vetorial: a Base fica só no texto.
    "local": None,
}


def has_embeddings(name: str) -> bool:
    """O provedor gera embeddings? O local não: a Base dele fica só no texto (ADR-0019)."""
    return EMBEDDING_MODELS.get(name) is not None


# Quem gera o embedding de cada índice (o do Vertex é sempre o compartilhado no Brasil).
INDEX_PROVIDERS = {VOYAGE_MODEL: "anthropic", EMBEDDING_MODEL: "vertex"}


@cache
def provider_for(name: str, project: str | None = None) -> LLMProvider:
    """Uma instância por provedor (e projeto) e processo: o cliente HTTP e o token são
    reaproveitados."""
    if name == "local":
        # Falha fechada: o modo local nunca cai num provedor em nuvem por este caminho.
        raise LLMUnavailableError("O perfil local é montado pelo worker com a configuração dele.")
    factory = PROVIDERS.get(name)
    if factory is None:
        raise LLMUnavailableError(f"Provedor de IA desconhecido: {name}.")
    return factory(project if name == "vertex_dedicated" else None)
