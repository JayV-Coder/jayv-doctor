"""Mapas de identificadores (ticket #40): todo Papel lê; Owner e Admin com MFA cadastram,
alteram e removem. Mudar um Mapa vale para os Eventos que chegarem depois."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from aid_api.core.auth import Claims, require_manager, require_role
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import MANAGE_CONNECTORS, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.correlation.repo import MappingRepository, get_mapping_repository
from aid_api.correlation.schemas import CorrelationMapping, MappingChange, MappingIn

router = APIRouter(
    prefix="/api/v1",
    tags=["correlation"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)
Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Manager = Annotated[Claims, Depends(require_manager(*MANAGE_CONNECTORS))]
Repository = Annotated[MappingRepository, Depends(get_mapping_repository)]


@router.get("/integrations/{target}/correlation-mappings", response_model=list[CorrelationMapping])
async def list_mappings(
    target: UUID, claims: Viewer, repository: Repository
) -> list[CorrelationMapping]:
    return await repository.list(claims, str(target))


@router.post(
    "/integrations/{target}/correlation-mappings",
    status_code=status.HTTP_201_CREATED,
    response_model=CorrelationMapping,
)
async def create_mapping(
    target: UUID, new: MappingIn, claims: Manager, repository: Repository, _: Idempotent
) -> CorrelationMapping:
    return await repository.create(claims, str(target), new)


@router.patch("/correlation-mappings/{target}", response_model=CorrelationMapping)
async def update_mapping(
    target: UUID, change: MappingChange, claims: Manager, repository: Repository, _: Idempotent
) -> CorrelationMapping:
    return await repository.update(claims, str(target), change)


@router.delete("/correlation-mappings/{target}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(
    target: UUID, claims: Manager, repository: Repository, _: Idempotent
) -> None:
    await repository.delete(claims, str(target))
