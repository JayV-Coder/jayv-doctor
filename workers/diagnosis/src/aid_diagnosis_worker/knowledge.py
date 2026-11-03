"""Indexação da Base de conhecimento (`knowledge.index`) e reindexação quando o provedor de IA
da Organização muda (o modelo de embedding junto). Fragmentos de modelos diferentes nunca se
misturam: o documento é refeito inteiro com o modelo atual. Só falha passageira (rede, 429, 5xx)
volta para o Pub/Sub; o resto marca o documento como `failed`, com o motivo, para a tela."""

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from aid_db import platform_role
from aid_diagnosis_engine.llm.base import LLMError, LLMProvider, LLMTransientError
from aid_knowledge.extract import ExtractionError
from aid_knowledge.index import index_document
from aid_knowledge.store import store_chunks
from aid_security.sanitizer import Sanitizer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

REINDEX_BATCH = 20
# Pedido de reindexação sem resposta nesse prazo (mensagem na DLQ, provedor fora) é refeito.
RETRY_AFTER = timedelta(hours=1)


class Store(Protocol):
    async def read(self, path: str) -> bytes | None: ...


ProviderFor = Callable[[str], LLMProvider]


async def fail(engine: AsyncEngine, document: Any, message: str) -> None:
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "update doctor.knowledge_documents set status = 'failed', error = :e,"
                " reindex_queued_at = null"
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
                    " d.body, t.llm_provider, t.llm_enabled from doctor.knowledge_documents d"
                    " join doctor.tenants t on t.id = d.tenant_id"
                    " where d.id = cast(:d as uuid) and d.status in ('indexing', 'ready')"
                ),
                {"d": str(payload["document_id"])},
            )
        ).first()
    if document is None:
        return "ignored"
    # Incidente promovido (#26): o texto está no registro; upload: o arquivo, no Storage.
    data = (
        document.body.encode()
        if document.body is not None
        else await store.read(document.storage_path)
    )
    if data is None:
        await fail(engine, document, "Arquivo não encontrado no armazenamento.")
        return "failed"
    # Envio ao LLM desligado (#29): nada sai para o provedor; os Fragmentos ficam só com o texto.
    provider = provider_for(document.llm_provider) if document.llm_enabled else None
    model = provider.embedding_model if provider is not None else None
    try:
        # Sem Referências de negócio aqui: o documento é texto livre, não um Evento.
        indexed, report = await index_document(data, document.content_type, Sanitizer(), provider)
    except ExtractionError as exc:
        await fail(engine, document, str(exc))
        return "failed"
    except LLMTransientError:
        # Passageira: a mensagem é reentregue; se esgotar, a reindexação refaz o pedido.
        raise
    except LLMError:
        # Recusa definitiva do provedor (credencial, pedido inválido): repetir não resolve.
        await fail(engine, document, "O provedor de IA recusou gerar os embeddings.")
        return "failed"
    except Exception:
        await fail(engine, document, "Não foi possível ler o arquivo.")
        return "failed"
    async with engine.begin() as connection:
        await platform_role(connection)
        await store_chunks(connection, document.tenant_id, document.id, indexed, model, report)
        await connection.execute(
            text(
                # Incidente promovido: o texto do registro vira o sanitizado (o bruto não fica).
                "update doctor.knowledge_documents set status = 'ready', error = null,"
                " chunk_count = :n, embedding_model = :m, reindex_queued_at = null,"
                " body = coalesce(:body, body)"
                " where tenant_id = cast(:t as uuid) and id = cast(:d as uuid)"
            ),
            {
                "t": document.tenant_id,
                "d": document.id,
                "n": len(indexed),
                "m": model,
                "body": str(Sanitizer().sanitize(document.body)[0])
                if document.body is not None
                else None,
            },
        )
    return "ready"


async def reindex_stale(engine: AsyncEngine, provider_for: ProviderFor) -> int:
    """Põe na fila (pela outbox) os documentos prontos cujo modelo não é o do provedor atual da
    Organização e os que ficaram em `indexing` sem resposta. O pronto continua `ready`: a busca
    por texto segue achando os Fragmentos antigos até os novos chegarem. O Cloud Scheduler chama
    a cada hora."""
    models = {name: provider_for(name).embedding_model for name in ("anthropic", "vertex")}
    async with engine.begin() as connection:
        await platform_role(connection)
        result = await connection.execute(
            text(
                "with stale as (select d.id, d.tenant_id from doctor.knowledge_documents d"
                " join doctor.tenants t on t.id = d.tenant_id"
                " where (d.status = 'indexing' and d.updated_at < cast(:cutoff as timestamptz)"
                " or d.status = 'ready' and t.llm_enabled and d.embedding_model is distinct from"
                " (cast(:models as jsonb) ->> t.llm_provider))"
                " and (d.reindex_queued_at is null"
                " or d.reindex_queued_at < cast(:cutoff as timestamptz))"
                " order by d.updated_at limit :n for update of d skip locked),"
                " moved as (update doctor.knowledge_documents d set reindex_queued_at = now()"
                " from stale where d.id = stale.id returning d.id, d.tenant_id)"
                " insert into doctor.outbox_messages (tenant_id, topic, payload)"
                " select tenant_id, 'knowledge.index', jsonb_build_object('document_id', id)"
                " from moved"
            ),
            {
                "models": json.dumps(models),
                "n": REINDEX_BATCH,
                "cutoff": datetime.now(UTC) - RETRY_AFTER,
            },
        )
        return result.rowcount or 0
