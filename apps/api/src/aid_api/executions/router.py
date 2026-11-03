"""Rotas do Explorador de Execuções (ticket #19). Todo Papel lê; o Log bruto é de Analyst para
cima, auditado, por URL assinada de 5 min."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from aid_api.core.auth import Claims, get_bearer_token, require_role
from aid_api.core.permissions import OPERATE, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.core.references import reference_of
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


@router.post("/executions/search", response_model=ExecutionPage)
async def search_executions(
    query: ExecutionSearch, claims: Viewer, repository: Repository
) -> ExecutionPage:
    return await repository.search(claims, query, reference_of(claims, query.q))


@router.get("/executions/{target}", response_model=ExecutionDetail)
async def get_execution(target: UUID, claims: Viewer, repository: Repository) -> ExecutionDetail:
    return await repository.detail(claims, str(target))


@router.get("/events/{target}", response_model=EventDetail)
async def get_event(
    target: UUID, claims: Viewer, repository: Repository, at: datetime | None = None
) -> EventDetail:
    """`at`: o instante do Evento (a Timeline manda), para ler só a partição dele."""
    return await repository.event(claims, str(target), at)


@router.get("/raw-logs/{target}/download", response_model=RawLogDownload)
async def download_raw_log(
    target: UUID, claims: Operator, token: Token, repository: Repository, storage: StorageDep
) -> RawLogDownload:
    async def sign(path: str) -> str:
        return await storage.sign_download(token, path, DOWNLOAD_SECONDS)

    url = await repository.raw_log_download(claims, str(target), sign)
    return RawLogDownload(url=url, expires_in=DOWNLOAD_SECONDS)
