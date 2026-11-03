"""Gravação e busca dos Fragmentos. A busca junta, por RRF, quatro listas: vetor e texto da
Organização, vetor e texto da Base global. O vetor só compara Fragmentos do mesmo modelo de
embedding (e o índice HNSW é por modelo); sem embedding da pergunta, fica só o texto. A
Organização entra na consulta explicitamente, além do RLS: o RAG nunca cruza tenants."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aid_knowledge.index import IndexedChunk
from aid_knowledge.search import rrf

# Dimensão de cada modelo de embedding conhecido (o índice HNSW parcial é por modelo).
DIMENSIONS = {"voyage-3": 1024, "text-embedding-005": 768, "fake": 8}
CANDIDATES = 20


@dataclass(frozen=True)
class Hit:
    origin: Literal["tenant", "global"]
    chunk_id: str
    document_id: str
    title: str
    heading: str | None
    content: str


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.7g}" for value in values) + "]"


def _vector_sql(table: str, documents: str, scope: str, dim: int) -> str:
    return (
        f"select c.id::text from doctor.{table} c join doctor.{documents} d on d.id = c.document_id"  # noqa: S608
        f" where c.embedding_model = :model{scope}"
        f" order by (c.embedding::extensions.vector({dim}))"
        f" operator(extensions.<=>) cast(:vector as extensions.vector({dim})) limit :n"
    )


# Qualquer termo da pergunta conta (OR), e o ranking decide: uma pergunta em linguagem natural
# raramente tem todas as palavras no mesmo Fragmento.
TSQUERY = "replace(plainto_tsquery('portuguese', :q)::text, ' & ', ' | ')::tsquery"


def _text_sql(table: str, documents: str, scope: str) -> str:
    return (
        f"select c.id::text from doctor.{table} c join doctor.{documents} d on d.id = c.document_id"  # noqa: S608
        f" where c.search_text @@ {TSQUERY}{scope}"
        f" order by ts_rank_cd(c.search_text, {TSQUERY}) desc"
        " limit :n"
    )


async def search(
    connection: AsyncConnection,
    tenant_id: str,
    query: str,
    *,
    embedding: Sequence[float] | None,
    model: str | None,
    k: int = 5,
) -> list[Hit]:
    tenant_scope = " and c.tenant_id = cast(:t as uuid) and d.status = 'ready'"
    params: dict[str, Any] = {"t": tenant_id, "q": query, "n": CANDIDATES}
    rankings: list[list[tuple[str, str]]] = []
    lists = [
        ("tenant", _text_sql("knowledge_chunks", "knowledge_documents", tenant_scope)),
        ("global", _text_sql("global_knowledge_chunks", "global_knowledge_documents", "")),
    ]
    dim = DIMENSIONS.get(model or "")
    if embedding is not None and dim is not None and len(embedding) == dim:
        params.update({"model": model, "vector": vector_literal(embedding)})
        lists += [
            ("tenant", _vector_sql("knowledge_chunks", "knowledge_documents", tenant_scope, dim)),
            (
                "global",
                _vector_sql("global_knowledge_chunks", "global_knowledge_documents", "", dim),
            ),
        ]
    for origin, sql in lists:
        found = await connection.execute(text(sql), params)
        rankings.append([(origin, row[0]) for row in found])
    chosen = rrf(rankings)[:k]
    return await _hits(connection, tenant_id, chosen)


async def _hits(
    connection: AsyncConnection, tenant_id: str, chosen: Sequence[tuple[str, str]]
) -> list[Hit]:
    tenant_ids = [chunk for origin, chunk in chosen if origin == "tenant"]
    global_ids = [chunk for origin, chunk in chosen if origin == "global"]
    rows: dict[tuple[str, str], Hit] = {}
    if tenant_ids:
        for row in await connection.execute(
            text(
                "select c.id::text, c.document_id::text, d.title, c.heading, c.content"
                " from doctor.knowledge_chunks c join doctor.knowledge_documents d"
                " on d.tenant_id = c.tenant_id and d.id = c.document_id"
                " where c.tenant_id = cast(:t as uuid) and c.id = any(cast(:ids as uuid[]))"
            ),
            {"t": tenant_id, "ids": tenant_ids},
        ):
            rows[("tenant", row[0])] = Hit("tenant", *row)
    if global_ids:
        for row in await connection.execute(
            text(
                "select c.id::text, c.document_id::text, d.title, c.heading, c.content"
                " from doctor.global_knowledge_chunks c join doctor.global_knowledge_documents d"
                " on d.id = c.document_id where c.id = any(cast(:ids as uuid[]))"
            ),
            {"ids": global_ids},
        ):
            rows[("global", row[0])] = Hit("global", *row)
    return [rows[item] for item in chosen if item in rows]


async def store_chunks(
    connection: AsyncConnection,
    tenant_id: str,
    document_id: str,
    indexed: Sequence[IndexedChunk],
    model: str,
    report: dict[str, int],
) -> None:
    """Troca os Fragmentos do documento pelos novos (reindexar é refazer, sem misturar)."""
    await connection.execute(
        text(
            "delete from doctor.knowledge_chunks"
            " where tenant_id = cast(:t as uuid) and document_id = cast(:d as uuid)"
        ),
        {"t": tenant_id, "d": document_id},
    )
    if indexed:
        await connection.execute(
            text(
                "insert into doctor.knowledge_chunks (tenant_id, document_id, ordinal, content,"
                " tokens, heading, embedding, embedding_model, metadata) values (cast(:t as uuid),"
                " cast(:d as uuid), :o, :c, :k, :h, cast(:e as extensions.vector), :m,"
                " cast(:meta as jsonb))"
            ),
            [
                {
                    "t": tenant_id,
                    "d": document_id,
                    "o": item.chunk.ordinal,
                    "c": item.chunk.content,
                    "k": item.chunk.tokens,
                    "h": item.chunk.heading,
                    "e": vector_literal(item.embedding),
                    "m": model,
                    "meta": json.dumps({"sanitization": report}),
                }
                for item in indexed
            ],
        )
