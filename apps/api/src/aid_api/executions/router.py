"""Rotas do Explorador de Execuções (ticket #19). Todo Papel lê; o Log bruto é de Analyst para
cima, auditado, por URL assinada de 5 min."""

import os
from typing import Annotated
from uuid import UUID

from aid_security.references import derive_tenant_key, reference_hmac
from fastapi import APIRouter, Depends

from aid_api.core.auth import Claims, get_bearer_token, require_role
from aid_api.core.permissions import OPERATE, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.core.storage import Storage, get_storage
from aid_api.executions.repo import ExecutionRepository, get_execution_repository
from aid_api.executions.schemas import (
    EventDetail,
    ExecutionDetail,
    ExecutionPage,
    ExecutionSearch,
    RawLogDownload,
)

DOWNLOAD_SECONDS = 300

router = APIRouter(prefix="/api/v1", tags=["executions"], dependencies=[Depends(rate_limit)])

Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Operator = Annotated[Claims, Depends(require_role(*OPERATE))]
Repository = Annotated[ExecutionRepository, Depends(get_execution_repository)]
StorageDep = Annotated[Storage, Depends(get_storage)]
Token = Annotated[str, Depends(get_bearer_token)]


def reference_of(claims: Claims, term: str | None) -> str | None:
    """O termo vira HMAC com a chave da Organização, como na ingestão: o número digitado nunca
    chega ao banco nem aos logs. Sem a chave configurada, a busca fica só pelos ids técnicos."""
    master = os.environ.get("HMAC_MASTER_KEY")
    if not term or not master or claims.tenant_id is None:
        return None
    return reference_hmac(derive_tenant_key(master.encode(), UUID(claims.tenant_id)), term)


@router.post("/executions/search", response_model=ExecutionPage)
async def search_executions(
    query: ExecutionSearch, claims: Viewer, repository: Repository
) -> ExecutionPage:
    return await repository.search(claims, query, reference_of(claims, query.q))


@router.get("/executions/{target}", response_model=ExecutionDetail)
async def get_execution(target: UUID, claims: Viewer, repository: Repository) -> ExecutionDetail:
    return await repository.detail(claims, str(target))


@router.get("/events/{target}", response_model=EventDetail)
async def get_event(target: UUID, claims: Viewer, repository: Repository) -> EventDetail:
    return await repository.event(claims, str(target))


@router.get("/raw-logs/{target}/download", response_model=RawLogDownload)
async def download_raw_log(
    target: UUID, claims: Operator, token: Token, repository: Repository, storage: StorageDep
) -> RawLogDownload:
    path = await repository.raw_log_path(claims, str(target))
    url = await storage.sign_download(token, path, DOWNLOAD_SECONDS)
    return RawLogDownload(url=url, expires_in=DOWNLOAD_SECONDS)
