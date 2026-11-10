"""O embedding da pergunta para a busca (ADR-0018): no modelo do perfil atual e, enquanto o
reindex não termina, nos índices antigos que o perfil ainda permite. Quem passou para o Brasil
não manda a pergunta ao Voyage: os Fragmentos antigos dele seguem achados pelo texto."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from aid_diagnosis_engine.llm.base import LLMError, LLMProvider
from aid_diagnosis_engine.llm.registry import INDEX_PROVIDERS, INDEXES

from aid_knowledge.store import vector_usable


@dataclass(frozen=True)
class QueryVectors:
    embedding: list[float] | None = None
    model: str | None = None
    previous: list[tuple[list[float], str]] = field(default_factory=list)

    @property
    def hybrid(self) -> bool:
        return vector_usable(self.embedding, self.model) or bool(self.previous)


async def query_vectors(
    query: str,
    provider: LLMProvider | None,
    profile: str,
    previous_models: Sequence[str],
    provider_for: Callable[[str], LLMProvider] | None,
) -> QueryVectors:
    """Sem provedor (envio ao LLM desligado), nada sai: a busca fica só no texto."""
    if provider is None:
        return QueryVectors()
    embedding: list[float] | None = None
    try:
        [embedding] = await provider.embed([query], input_type="query")
    except LLMError:
        embedding = None
    model = provider.embedding_model if vector_usable(embedding, provider.embedding_model) else None
    previous: list[tuple[list[float], str]] = []
    allowed = INDEXES.get(profile, frozenset())
    for old_model in previous_models if provider_for is not None else ():
        name = INDEX_PROVIDERS.get(old_model)
        if old_model not in allowed or name is None or old_model == provider.embedding_model:
            continue
        try:
            [vector] = await provider_for(name).embed([query], input_type="query")  # type: ignore[misc]
        except LLMError:
            continue
        previous.append((vector, old_model))
    return QueryVectors(embedding if model else None, model, previous)
