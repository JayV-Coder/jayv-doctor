"""Busca da Base de conhecimento contra Postgres real (INTEGRATION_DB_URL, job de E2E do CI)."""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from aid_diagnosis_engine.llm.fake import FakeProvider
from aid_knowledge.chunking import chunk_text
from aid_knowledge.global_seed import documents, sync
from aid_knowledge.index import embed_chunks
from aid_knowledge.store import search, store_chunks
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


async def tenant_with_document(engine: AsyncEngine, body: str, title: str) -> tuple[str, str]:
    tenant, document = str(uuid4()), str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text("insert into public.organizations (id, name, slug) values (:t, 'T', :s)"),
            {"t": tenant, "s": f"t-{tenant[:30]}"},
        )
        await connection.execute(text("insert into doctor.tenants (id) values (:t)"), {"t": tenant})
        await connection.execute(
            text(
                "insert into doctor.knowledge_documents (id, tenant_id, title, source,"
                " storage_path, content_type, size_bytes, status) values (:d, :t, :title,"
                " 'upload', :p, 'text/markdown', 10, 'ready')"
            ),
            {"d": document, "t": tenant, "title": title, "p": f"{tenant}/{document}/doc.md"},
        )
        indexed = await embed_chunks(FakeProvider(), chunk_text(body))
        await store_chunks(connection, tenant, document, indexed, "fake", {})
    return tenant, document


async def drop(engine: AsyncEngine, tenant: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("delete from doctor.tenants where id = :t"), {"t": tenant})
        await connection.execute(
            text("delete from public.organizations where id = :t"), {"t": tenant}
        )


@pytest.mark.asyncio
async def test_rag_nunca_cruza_organizacoes(engine: AsyncEngine) -> None:
    body = "# Runbook\n\nO job VL10 trava quando a remessa está bloqueada pelo crédito."
    first, first_doc = await tenant_with_document(engine, body, "Runbook A")
    second, _ = await tenant_with_document(engine, body + " Versão B.", "Runbook B")
    try:
        query = "remessa bloqueada crédito VL10"
        [vector] = await FakeProvider().embed([query], input_type="query")
        async with engine.begin() as connection:
            hits = await search(connection, first, query, embedding=vector, model="fake", k=10)
        tenant_hits = [hit for hit in hits if hit.origin == "tenant"]
        assert tenant_hits
        assert {hit.document_id for hit in tenant_hits} == {first_doc}
        assert all(hit.origin in ("tenant", "global") for hit in hits)
    finally:
        await drop(engine, first)
        await drop(engine, second)


@pytest.mark.asyncio
async def test_vetor_de_outro_modelo_nao_entra_na_busca(engine: AsyncEngine) -> None:
    tenant, _ = await tenant_with_document(engine, "# Doc\n\nconteúdo xyzzy único", "Doc")
    try:
        async with engine.begin() as connection:
            # Pergunta com embedding de outro modelo e sem palavra em comum: nada volta.
            hits = await search(
                connection, tenant, "palavrainexistente", embedding=[0.1] * 1024, model="voyage-3"
            )
        assert [hit for hit in hits if hit.origin == "tenant"] == []
    finally:
        await drop(engine, tenant)


QUESTIONS = [
    (
        "BAPI respondeu 200 mas o pedido não foi criado, tabela RETURN com tipo E",
        "sap-sd-mensagens",
    ),
    ("mensagem da classe VL ao criar remessa", "sap-sd-mensagens"),
    ("objeto bloqueado por outro usuário no SAP", "sap-sd-mensagens"),
    ("o que fazer depois de um 504 do gateway", "http-rest-erros"),
    ("Retry-After e limite de taxa 429", "http-rest-erros"),
    ("409 conflito depois de timeout", "http-rest-erros"),
    ("REQUEST_LIMIT_EXCEEDED cota diária de API", "salesforce-limites"),
    ("UNABLE_TO_LOCK_ROW cargas paralelas", "salesforce-limites"),
    ("INVALID_SESSION_ID refresh token revogado", "salesforce-limites"),
    ("roles/logging.viewer PERMISSION_DENIED ao ler logs", "gcp-cloud-run-logging"),
    ("partida a frio Cloud Run instâncias mínimas", "gcp-cloud-run-logging"),
    ("memória excedida instância encerrada", "gcp-cloud-run-logging"),
    ("IDoc com status 51 documento de aplicação não lançado", "sap-mm-fi-idoc"),
    ("material não mantido no centro M3 305", "sap-mm-fi-idoc"),
    ("chamadas tRFC pendentes na SM58", "sap-mm-fi-idoc"),
]


@pytest.mark.asyncio
async def test_recall_at_5_da_base_global(engine: AsyncEngine) -> None:
    await sync(engine)
    assert len(documents()) == 5
    tenant, _ = await tenant_with_document(engine, "# Nada\n\nsem relação", "Outro")
    try:
        found = 0
        async with engine.begin() as connection:
            slugs = {
                row[0]: row[1]
                for row in await connection.execute(
                    text("select id::text, slug from doctor.global_knowledge_documents")
                )
            }
            for question, expected in QUESTIONS:
                hits = await search(connection, tenant, question, embedding=None, model=None)
                if expected in {
                    slugs.get(hit.document_id) for hit in hits if hit.origin == "global"
                }:
                    found += 1
        assert found / len(QUESTIONS) >= 0.8, found
    finally:
        await drop(engine, tenant)
