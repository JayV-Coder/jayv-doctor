"""Rotas de Integrações: todo Papel lê; Owner e Admin com MFA cadastram, alteram e arquivam."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from aid_api.core.auth import Claims, require_manager, require_role
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import MANAGE_CONNECTORS, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.integrations.repo import IntegrationRepository, get_integration_repository
from aid_api.integrations.schemas import Integration, IntegrationChange, NewIntegration

router = APIRouter(
    prefix="/api/v1/integrations",
    tags=["integrations"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)


Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Manager = Annotated[Claims, Depends(require_manager(*MANAGE_CONNECTORS))]
Integrations = Annotated[IntegrationRepository, Depends(get_integration_repository)]


@router.get("", response_model=list[Integration])
async def list_integrations(
    claims: Viewer, repository: Integrations, include_archived: bool = False
) -> list[Integration]:
    return await repository.list(claims, include_archived=include_archived)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Integration)
async def create_integration(
    new: NewIntegration, claims: Manager, repository: Integrations, _: Idempotent
) -> Integration:
    return await repository.create(claims, new)


@router.patch("/{target}", response_model=Integration)
async def update_integration(
    target: UUID,
    change: IntegrationChange,
    claims: Manager,
    repository: Integrations,
    _: Idempotent,
) -> Integration:
    return await repository.update(claims, str(target), change)


# Sem exclusão física: Execuções e Incidentes apontam para a Integração.
@router.post("/{target}/archive", response_model=Integration)
async def archive_integration(
    target: UUID, claims: Manager, repository: Integrations, _: Idempotent
) -> Integration:
    return await repository.archive(claims, str(target))
