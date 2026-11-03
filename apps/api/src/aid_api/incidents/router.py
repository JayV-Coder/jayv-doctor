"""Rotas de Incidentes (ticket #20). Todo Papel lê; Analyst ou acima muda status, severidade e
responsável e comenta, com o Papel conferido de novo no banco."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from aid_api.core.auth import Claims, require_role
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import OPERATE, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.core.references import reference_of
from aid_api.incidents.repo import IncidentRepository, get_incident_repository
from aid_api.incidents.schemas import (
    Comment,
    IncidentChange,
    IncidentDetail,
    IncidentPage,
    IncidentSearch,
    NewComment,
)

router = APIRouter(
    prefix="/api/v1/incidents",
    tags=["incidents"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)

Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Operator = Annotated[Claims, Depends(require_role(*OPERATE))]
Repository = Annotated[IncidentRepository, Depends(get_incident_repository)]


@router.post("/search", response_model=IncidentPage)
async def search_incidents(
    query: IncidentSearch, claims: Viewer, repository: Repository
) -> IncidentPage:
    return await repository.search(claims, query, reference_of(claims, query.q))


@router.get("/{target}", response_model=IncidentDetail)
async def get_incident(target: UUID, claims: Viewer, repository: Repository) -> IncidentDetail:
    return await repository.detail(claims, str(target))


@router.patch("/{target}", response_model=IncidentDetail)
async def update_incident(
    target: UUID, change: IncidentChange, claims: Operator, repository: Repository, _: Idempotent
) -> IncidentDetail:
    return await repository.update(claims, str(target), change)


@router.get("/{target}/comments", response_model=list[Comment])
async def list_comments(target: UUID, claims: Viewer, repository: Repository) -> list[Comment]:
    return await repository.comments(claims, str(target))


@router.post("/{target}/comments", status_code=status.HTTP_201_CREATED, response_model=Comment)
async def add_comment(
    target: UUID, new: NewComment, claims: Operator, repository: Repository, _: Idempotent
) -> Comment:
    return await repository.comment(claims, str(target), new)
