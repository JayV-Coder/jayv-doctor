"""Rotas da Base de conhecimento (ticket #23). Todo Papel lê e busca; Analyst ou acima envia e
remove documentos. O arquivo sobe direto do navegador para o Storage, como nas Importações."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from aid_diagnosis_engine.llm import LLMError, LLMProvider, provider_for
from aid_knowledge.store import vector_usable
from fastapi import APIRouter, Depends, Response, status

from aid_api.core.auth import Claims, get_bearer_token, require_role
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import OPERATE, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.core.storage import Storage, get_storage
from aid_api.knowledge.repo import KnowledgeRepository, get_knowledge_repository
from aid_api.knowledge.schemas import (
    CreatedKnowledgeDocument,
    GlobalDocument,
    KnowledgeDocument,
    KnowledgeQuery,
    KnowledgeResults,
    NewKnowledgeDocument,
)

BUCKET = "doctor-knowledge"

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)

Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Operator = Annotated[Claims, Depends(require_role(*OPERATE))]
Repository = Annotated[KnowledgeRepository, Depends(get_knowledge_repository)]
StorageDep = Annotated[Storage, Depends(get_storage)]
Token = Annotated[str, Depends(get_bearer_token)]


def get_provider_for() -> Callable[[str], LLMProvider]:
    return provider_for


ProviderFor = Annotated[Callable[[str], LLMProvider], Depends(get_provider_for)]


@router.get("/documents", response_model=list[KnowledgeDocument])
async def list_documents(claims: Viewer, repository: Repository) -> list[KnowledgeDocument]:
    return await repository.documents(claims)


@router.get("/global", response_model=list[GlobalDocument])
async def list_global(claims: Viewer, repository: Repository) -> list[GlobalDocument]:
    return await repository.global_documents(claims)


@router.post(
    "/documents", status_code=status.HTTP_201_CREATED, response_model=CreatedKnowledgeDocument
)
async def create_document(
    new: NewKnowledgeDocument,
    claims: Operator,
    token: Token,
    repository: Repository,
    storage: StorageDep,
    _: Idempotent,
) -> CreatedKnowledgeDocument:
    created, path = await repository.create(claims, new)
    return CreatedKnowledgeDocument(
        id=created, upload_url=await storage.sign_upload(token, path, BUCKET)
    )


# Upload concluído: o documento vai para a fila de indexação.
@router.post("/documents/{target}/finish", status_code=status.HTTP_202_ACCEPTED)
async def finish_document(target: UUID, claims: Operator, repository: Repository) -> Response:
    await repository.finish(claims, str(target))
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.delete("/documents/{target}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    target: UUID, claims: Operator, token: Token, repository: Repository, storage: StorageDep
) -> Response:
    # Arquivo primeiro: se o Storage falhar, o registro fica e a remoção pode ser repetida; o
    # contrário deixaria o original (nunca sanitizado) no bucket sem caminho para apagá-lo.
    path = await repository.storage_path(claims, str(target))
    if path:
        await storage.delete(token, path, BUCKET)
    await repository.delete(claims, str(target))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/search", response_model=KnowledgeResults)
async def search_knowledge(
    query: KnowledgeQuery, claims: Viewer, repository: Repository, providers: ProviderFor
) -> KnowledgeResults:
    """Híbrida (vetor + texto, RRF) com o embedding do provedor da Organização; com o provedor
    fora, só o texto, em vez de falhar. O provedor sai numa transação curta e o embedding é
    gerado fora dela: nenhuma conexão do banco fica presa esperando a API de IA."""
    provider = providers(await repository.llm_provider(claims))
    embedding: list[float] | None = None
    try:
        [embedding] = await provider.embed([query.q], input_type="query")
    except LLMError:
        embedding = None
    model = provider.embedding_model
    hybrid = vector_usable(embedding, model)
    items = await repository.search(
        claims, query.q, query.k, embedding if hybrid else None, model if hybrid else None
    )
    return KnowledgeResults(items=items, mode="hybrid" if hybrid else "text")
