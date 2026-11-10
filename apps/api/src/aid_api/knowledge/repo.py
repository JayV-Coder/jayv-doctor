"""Base de conhecimento dentro de `tenant_tx`: leitura pelo RLS; escrita pelas funções do banco,
que conferem Analyst ou acima na tabela. A busca usa o mesmo código do worker de diagnóstico."""

from collections.abc import Sequence
from dataclasses import dataclass

from aid_knowledge.store import previous_models, search
from sqlalchemy import text

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.knowledge.schemas import (
    GlobalDocument,
    KnowledgeDocument,
    KnowledgeHit,
    NewKnowledgeDocument,
)

EXCERPT = 600


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Documento não encontrado.")


ERRORS = {
    "P0002": not_found,
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "22023": lambda: ApiError(422, "invalid_filename", "Nome de arquivo inválido."),
}


@dataclass(frozen=True)
class AiChoice:
    provider: str | None
    project: str | None
    profile: str
    models: list[str]


class KnowledgeRepository:
    async def documents(self, claims: Claims) -> list[KnowledgeDocument]:
        async with translated_tx(claims, ERRORS) as connection:
            result = await connection.execute(
                text(
                    "select id::text, title, source, status, content_type, size_bytes,"
                    " chunk_count, error, created_at from doctor.knowledge_documents"
                    " order by created_at desc limit 200"
                )
            )
            return [KnowledgeDocument.model_validate(dict(row)) for row in result.mappings()]

    async def global_documents(self, claims: Claims) -> list[GlobalDocument]:
        async with translated_tx(claims, ERRORS) as connection:
            result = await connection.execute(
                text(
                    "select id::text, slug, title, chunk_count"
                    " from doctor.global_knowledge_documents order by title"
                )
            )
            return [GlobalDocument.model_validate(dict(row)) for row in result.mappings()]

    async def create(self, claims: Claims, new: NewKnowledgeDocument) -> tuple[str, str]:
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                await connection.execute(
                    text(
                        "select id::text, storage_path"
                        " from doctor.create_knowledge_document(:t, :f, :c, :s)"
                    ),
                    {"t": new.title, "f": new.filename, "c": new.content_type, "s": new.size_bytes},
                )
            ).one()
            return row.id, row.storage_path

    async def storage_path(self, claims: Claims, target: str) -> str | None:
        """Caminho do arquivo (documento de Incidente não tem); 404 se o documento não existe."""
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                await connection.execute(
                    text(
                        "select storage_path from doctor.knowledge_documents"
                        " where id = cast(:d as uuid)"
                    ),
                    {"d": target},
                )
            ).first()
        if row is None:
            raise not_found()
        return str(row.storage_path) if row.storage_path else None

    async def finish(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(
                text("select doctor.finish_knowledge_upload(cast(:d as uuid))"), {"d": target}
            )

    async def delete(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(
                text("select doctor.delete_knowledge_document(cast(:d as uuid))"), {"d": target}
            )

    async def ai(self, claims: Claims) -> AiChoice:
        """Provedor e perfil de IA da Organização (provedor `None` se ela desligou o envio ao
        LLM, #29) e os modelos de embedding dos documentos prontos (ADR-0018)."""
        async with translated_tx(claims, ERRORS) as connection:
            found = (
                await connection.execute(
                    text(
                        "select llm_provider, llm_enabled, ai_profile, ai_project"
                        " from doctor.tenants where id = (select doctor.current_tenant_id())"
                    )
                )
            ).first()
            models = await previous_models(connection, claims.tenant_id or "", None)
        if found is None:
            return AiChoice("anthropic", None, "standard", models)
        return AiChoice(
            str(found.llm_provider) if found.llm_enabled else None,
            found.ai_project,
            str(found.ai_profile),
            models,
        )

    async def search(
        self,
        claims: Claims,
        query: str,
        k: int,
        embedding: Sequence[float] | None,
        model: str | None,
        previous: Sequence[tuple[Sequence[float], str]] = (),
    ) -> list[KnowledgeHit]:
        # require_role já garante a Organização ativa; o RLS limita de novo.
        tenant = claims.tenant_id or ""
        async with translated_tx(claims, ERRORS) as connection:
            hits = await search(
                connection,
                tenant,
                query,
                embedding=embedding,
                model=model,
                k=k,
                previous=previous,
            )
        return [
            KnowledgeHit(
                origin=hit.origin,
                document_id=hit.document_id,
                title=hit.title,
                heading=hit.heading,
                excerpt=hit.content[:EXCERPT],
            )
            for hit in hits
        ]


def get_knowledge_repository() -> KnowledgeRepository:
    return KnowledgeRepository()
