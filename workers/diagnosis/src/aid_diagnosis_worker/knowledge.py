"""Indexação da Base de conhecimento (`knowledge.index`) e reindexação quando o provedor de IA
da Organização muda (o modelo de embedding junto). Fragmentos de modelos diferentes nunca se
misturam: o documento é refeito inteiro com o modelo atual."""

import json
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from aid_db import platform_role
from aid_diagnosis_engine.llm.base import LLMError, LLMProvider
from aid_knowledge.extract import ExtractionError
from aid_knowledge.index import index_document
from aid_knowledge.store import store_chunks
from aid_security.sanitizer import Sanitizer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

REINDEX_BATCH = 20


class Store(Protocol):
    async def read(self, path: str) -> bytes | None: ...


ProviderFor = Callable[[str], LLMProvider]


async def fail(engine: AsyncEngine, document: Any, message: str) -> None:
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "update doctor.knowledge_documents set status = 'failed', error = :e"
                " where tenant_id = cast(:t as uuid) and id = cast(:d as uuid)"
            ),
            {"t": document.tenant_id, "d": document.id, "e": message[:500]},
        )


async def index(
    engine: AsyncEngine, payload: Mapping[str, Any], store: Store, provider_for: ProviderFor
) -> str:
    async with engine.begin() as connection:
        await platform_role(connection)
        document = (
            await connection.execute(
                text(
                    "select d.id::text, d.tenant_id::text, d.storage_path, d.content_type,"
                    " t.llm_provider from doctor.knowledge_documents d"
                    " join doctor.tenants t on t.id = d.tenant_id"
                    " where d.id = cast(:d as uuid) and d.status in ('indexing', 'ready')"
                ),
                {"d": str(payload["document_id"])},
            )
        ).first()
    if document is None:
        return "ignored"
    data = await store.read(document.storage_path)
    if data is None:
        await fail(engine, document, "Arquivo não encontrado no armazenamento.")
        return "failed"
    provider = provider_for(document.llm_provider)
    try:
        # Sem Referências de negócio aqui: o documento é texto livre, não um Evento.
        indexed, report = await index_document(data, document.content_type, Sanitizer(), provider)
    except ExtractionError as exc:
        await fail(engine, document, str(exc))
        return "failed"
    except LLMError:
        # Provedor fora: a mensagem é reentregue e o documento continua `indexing`.
        raise
    async with engine.begin() as connection:
        await platform_role(connection)
        await store_chunks(
            connection, document.tenant_id, document.id, indexed, provider.embedding_model, report
        )
        await connection.execute(
            text(
                "update doctor.knowledge_documents set status = 'ready', error = null,"
                " chunk_count = :n, embedding_model = :m"
                " where tenant_id = cast(:t as uuid) and id = cast(:d as uuid)"
            ),
            {
                "t": document.tenant_id,
                "d": document.id,
                "n": len(indexed),
                "m": provider.embedding_model,
            },
        )
    return "ready"


async def reindex_stale(engine: AsyncEngine, provider_for: ProviderFor) -> int:
    """Documentos prontos cujo modelo não é o do provedor atual da Organização voltam para a
    fila de indexação (pela outbox). O Cloud Scheduler chama a cada hora."""
    models = {name: provider_for(name).embedding_model for name in ("anthropic", "vertex")}
    async with engine.begin() as connection:
        await platform_role(connection)
        result = await connection.execute(
            text(
                "with stale as (select d.id, d.tenant_id from doctor.knowledge_documents d"
                " join doctor.tenants t on t.id = d.tenant_id"
                " where d.status = 'ready' and d.source = 'upload'"
                " and d.embedding_model is distinct from"
                " (cast(:models as jsonb) ->> t.llm_provider)"
                " order by d.updated_at limit :n for update of d skip locked),"
                " moved as (update doctor.knowledge_documents d set status = 'indexing'"
                " from stale where d.id = stale.id returning d.id, d.tenant_id)"
                " insert into doctor.outbox_messages (tenant_id, topic, payload)"
                " select tenant_id, 'knowledge.index', jsonb_build_object('document_id', id)"
                " from moved"
            ),
            {"models": json.dumps(models), "n": REINDEX_BATCH},
        )
        return result.rowcount or 0
