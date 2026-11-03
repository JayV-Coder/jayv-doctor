"""Indexa, como o worker de diagnóstico, os documentos enviados pela Organização do E2E da Base
de conhecimento (ticket #23), com o FakeProvider no lugar do provedor de IA. Roda com
`uv run python` na raiz do repositório.

Uso: seed_knowledge.py <nome da Organização>
"""

import asyncio
import os
import sys

from aid_diagnosis_engine.llm.fake import FakeProvider
from aid_diagnosis_worker.knowledge import index
from aid_knowledge.storage import KnowledgeStore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

DB = os.environ.get("E2E_DB_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres")


async def main(organization: str) -> None:
    engine = create_async_engine(DB, poolclass=NullPool)
    store = KnowledgeStore(
        os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321"),
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    provider = FakeProvider()
    async with engine.begin() as connection:
        documents = (
            await connection.execute(
                text(
                    "select d.id::text from doctor.knowledge_documents d"
                    " join public.organizations o on o.id = d.tenant_id"
                    " where o.name = :name and d.status = 'indexing'"
                ),
                {"name": organization},
            )
        ).scalars()
        targets = list(documents)
    for document in targets:
        await index(engine, {"document_id": document}, store, lambda _: provider)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
