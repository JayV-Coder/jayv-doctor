"""Base global v1: os textos de `global_base/` (escritos pela equipe, sem copiar documentação
proprietária) viram documentos e Fragmentos da Base global. Roda como job de plataforma no
deploy (`python -m aid_knowledge.global_seed`); só refaz o documento cujo texto mudou, e gera os
embeddings com o provedor padrão quando há credencial (sem ela, a busca usa só o texto)."""

import asyncio
import hashlib
import json
import os
from importlib import resources

from aid_db import platform_role, supavisor_engine
from aid_diagnosis_engine.llm.base import LLMError, LLMProvider
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_knowledge.chunking import chunk_text
from aid_knowledge.index import embed_chunks
from aid_knowledge.store import vector_literal


def documents() -> list[tuple[str, str, str]]:
    """(slug, título, texto) de cada arquivo da Base global."""
    found = []
    for item in sorted(resources.files("aid_knowledge.global_base").iterdir(), key=str):
        if item.name.endswith(".md"):
            body = item.read_text(encoding="utf-8")
            title = body.splitlines()[0].lstrip("# ").strip()
            found.append((item.name.removesuffix(".md"), title, body))
    return found


async def sync(engine: AsyncEngine, provider: LLMProvider | None = None) -> int:
    """Devolve quantos documentos foram (re)gravados."""
    changed = 0
    for slug, title, body in documents():
        version = hashlib.sha256(body.encode()).hexdigest()[:16]
        chunks = chunk_text(body)
        vectors: list[list[float] | None] = [None] * len(chunks)
        model: str | None = None
        async with engine.begin() as connection:
            await platform_role(connection)
            current = await connection.scalar(
                text("select version from doctor.global_knowledge_documents where slug = :s"),
                {"s": slug},
            )
        if current == version:
            continue
        if provider is not None:
            try:
                indexed = await embed_chunks(provider, chunks)
                vectors = [item.embedding for item in indexed]
                model = provider.embedding_model
            except LLMError:
                vectors = [None] * len(chunks)
        async with engine.begin() as connection:
            await platform_role(connection)
            document_id = await connection.scalar(
                text(
                    "insert into doctor.global_knowledge_documents (slug, title, version,"
                    " chunk_count) values (:s, :t, :v, :n) on conflict (slug) do update set"
                    " title = excluded.title, version = excluded.version,"
                    " chunk_count = excluded.chunk_count returning id::text"
                ),
                {"s": slug, "t": title, "v": version, "n": len(chunks)},
            )
            await connection.execute(
                text(
                    "delete from doctor.global_knowledge_chunks"
                    " where document_id = cast(:d as uuid)"
                ),
                {"d": document_id},
            )
            await connection.execute(
                text(
                    "insert into doctor.global_knowledge_chunks (document_id, ordinal, content,"
                    " tokens, heading, embedding, embedding_model, metadata) values"
                    " (cast(:d as uuid), :o, :c, :k, :h, cast(:e as extensions.vector), :m,"
                    " cast(:meta as jsonb))"
                ),
                [
                    {
                        "d": document_id,
                        "o": chunk.ordinal,
                        "c": chunk.content,
                        "k": chunk.tokens,
                        "h": chunk.heading,
                        "e": vector_literal(vector) if vector is not None else None,
                        "m": model if vector is not None else None,
                        "meta": json.dumps({"slug": slug}),
                    }
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )
        changed += 1
    return changed


def main() -> None:
    from aid_diagnosis_engine.llm.registry import provider_for

    engine = supavisor_engine(os.environ["SUPABASE_DB_URL"])
    provider = provider_for("anthropic") if os.environ.get("VOYAGE_API_KEY") else None
    print(f"Base global: {asyncio.run(sync(engine, provider))} documento(s) atualizados.")  # noqa: T201


if __name__ == "__main__":
    main()
