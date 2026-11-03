"""Do arquivo aos Fragmentos prontos para gravar: extrai, sanitiza (antes do embedding: segredo e
dado pessoal nunca viram vetor), fragmenta e gera o embedding pelo provedor da Organização."""

from collections.abc import Sequence
from dataclasses import dataclass

from aid_diagnosis_engine.llm.base import LLMProvider
from aid_security.sanitizer import Sanitizer

from aid_knowledge.chunking import Chunk, chunk_text
from aid_knowledge.extract import extract_text


@dataclass(frozen=True)
class IndexedChunk:
    chunk: Chunk
    embedding: list[float]


async def embed_chunks(provider: LLMProvider, chunks: Sequence[Chunk]) -> list[IndexedChunk]:
    """O provedor divide em lotes conforme os limites de itens e tokens da API dele."""
    vectors = await provider.embed([c.content for c in chunks], input_type="document")
    return [IndexedChunk(c, v) for c, v in zip(chunks, vectors, strict=True)]


async def index_document(
    data: bytes, content_type: str, sanitizer: Sanitizer, provider: LLMProvider
) -> tuple[list[IndexedChunk], dict[str, int]]:
    """(Fragmentos com embedding, contagem do que a Sanitização tirou)."""
    clean, report = sanitizer.sanitize(extract_text(data, content_type))
    chunks = chunk_text(str(clean))
    return await embed_chunks(provider, chunks), dict(report.counts)
