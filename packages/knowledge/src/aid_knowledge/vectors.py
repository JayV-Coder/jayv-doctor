"""O embedding da pergunta para a busca (ADR-0018): no modelo do perfil atual e, enquanto o
reindex não termina, nos índices antigos que o perfil ainda permite. Quem passou para o Brasil
não manda a pergunta ao Voyage: os Fragmentos antigos dele seguem achados pelo texto."""

import asyncio
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
    provider_for: Callable[[str], LLMProvider],
) -> QueryVectors:
    """Sem provedor (envio ao LLM desligado), nada sai: a busca fica só no texto. Os
    embeddings (do modelo atual e dos índices antigos) saem em paralelo."""
    if provider is None:
        return QueryVectors()
    allowed = INDEXES.get(profile, frozenset())
    olds = [
        (old_model, name)
        for old_model in previous_models
        if old_model in allowed
        and old_model != provider.embedding_model
        and (name := INDEX_PROVIDERS.get(old_model)) is not None
    ]

    async def embed(chosen: LLMProvider) -> list[float] | None:
        try:
            [vector] = await chosen.embed([query], input_type="query")
        except LLMError:
            return None
        return vector

    found = await asyncio.gather(embed(provider), *(embed(provider_for(name)) for _, name in olds))
    embedding = found[0]
    model = provider.embedding_model if vector_usable(embedding, provider.embedding_model) else None
    previous = [
        (vector, old_model)
        for (old_model, _), vector in zip(olds, found[1:], strict=True)
        if vector is not None
    ]
    return QueryVectors(embedding if model else None, model, previous)
