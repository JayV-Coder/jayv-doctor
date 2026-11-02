"""Rotas de Importação manual (ticket #11): o arquivo sobe direto do navegador para o Storage."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from aid_api.core.auth import Claims, get_bearer_token, require_role
from aid_api.core.errors import ApiError
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import IMPORT_LOGS, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.imports.content import HEAD_BYTES, check_head
from aid_api.imports.repo import ImportRepository, get_import_repository, not_pending
from aid_api.imports.schemas import CreatedImport, Import, NewImport
from aid_api.imports.storage import Storage, get_storage

router = APIRouter(
    prefix="/api/v1/imports",
    tags=["imports"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)

Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Importer = Annotated[Claims, Depends(require_role(*IMPORT_LOGS))]
Imports = Annotated[ImportRepository, Depends(get_import_repository)]
StorageDep = Annotated[Storage, Depends(get_storage)]
Token = Annotated[str, Depends(get_bearer_token)]


@router.get("", response_model=list[Import])
async def list_imports(claims: Viewer, repository: Imports) -> list[Import]:
    return await repository.list(claims)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreatedImport)
async def create_import(
    new: NewImport,
    claims: Importer,
    token: Token,
    repository: Imports,
    storage: StorageDep,
    _: Idempotent,
) -> CreatedImport:
    created = await repository.create(claims, new)
    upload_url = None
    if created.storage_path is not None:
        upload_url = await storage.sign_upload(token, created.storage_path)
    return CreatedImport(
        id=created.id,
        status=created.status,
        error=created.error,
        duplicate_of=created.duplicate_of,
        upload_url=upload_url,
    )


# Confere o começo do arquivo e só então enfileira o processamento: conteúdo de outro formato
# vira Importação `rejected`, com o motivo, sem chegar ao worker.
@router.post("/{target}/complete", response_model=Import)
async def complete_import(
    target: UUID,
    claims: Importer,
    token: Token,
    repository: Imports,
    storage: StorageDep,
    _: Idempotent,
) -> Import:
    current, path = await repository.get(claims, str(target))
    if current.status != "pending" or current.format is None:
        raise not_pending()
    head = await storage.head(token, path, HEAD_BYTES)
    if head is None:
        raise ApiError(409, "upload_missing", "O arquivo ainda não chegou ao armazenamento.")
    reason = check_head(current.format, head.data, head.size)
    if reason is not None:
        return await repository.reject(claims, str(target), reason, head.size)
    return await repository.complete(claims, str(target), head.size)
