"""Rotas de Conectores (ticket #14). Todo Papel lê; Owner e Admin com MFA gerenciam. A credencial
entra pelo POST/PATCH e vai direto para o Vault: nenhuma resposta a traz, nem mascarada."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from aid_api.connectors import service
from aid_api.connectors.repo import ConnectorRepository, get_connector_repository
from aid_api.connectors.schemas import (
    ConnectionTest,
    Connector,
    ConnectorChange,
    ConnectorSync,
    NewConnectionTest,
    NewConnector,
    TestResult,
)
from aid_api.core.auth import Claims, require_aal2_claims, require_role
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import MANAGE_CONNECTORS, VIEW
from aid_api.core.rate_limit import rate_limit

router = APIRouter(
    prefix="/api/v1/connectors",
    tags=["connectors"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)


def require_manager(
    claims: Annotated[Claims, Depends(require_role(*MANAGE_CONNECTORS))],
) -> Claims:
    return require_aal2_claims(claims)


Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Manager = Annotated[Claims, Depends(require_manager)]
Repository = Annotated[ConnectorRepository, Depends(get_connector_repository)]


@router.get("", response_model=list[Connector])
async def list_connectors(claims: Viewer, repository: Repository) -> list[Connector]:
    return await repository.all(claims)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Connector)
async def create_connector(
    new: NewConnector, claims: Manager, repository: Repository, _: Idempotent
) -> Connector:
    service.check_config(new.provider, new.config)
    return await repository.create(claims, new)


# Antes de `/{target}`: senão "test" seria lido como id.
@router.post("/test", response_model=TestResult)
async def test_new_connection(request: NewConnectionTest, claims: Manager) -> TestResult:
    return await service.test_connection(
        request.provider, request.config, request.credential.get_secret_value()
    )


@router.get("/{target}", response_model=Connector)
async def get_connector(target: UUID, claims: Viewer, repository: Repository) -> Connector:
    return await repository.get(claims, str(target))


@router.patch("/{target}", response_model=Connector)
async def update_connector(
    target: UUID, change: ConnectorChange, claims: Manager, repository: Repository, _: Idempotent
) -> Connector:
    if change.config is not None:
        current = await repository.get(claims, str(target))
        service.check_config(current.provider, change.config)
    return await repository.update(claims, str(target), change)


@router.post("/{target}/test", response_model=TestResult)
async def test_connection(
    target: UUID, request: ConnectionTest, claims: Manager, repository: Repository
) -> TestResult:
    current = await repository.get(claims, str(target))
    return await service.test_connection(
        current.provider, current.config, request.credential.get_secret_value()
    )


@router.post("/{target}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_connector(
    target: UUID, claims: Manager, repository: Repository, _: Idempotent
) -> None:
    await repository.action(claims, str(target), "sync")


@router.post("/{target}/pause", status_code=status.HTTP_204_NO_CONTENT)
async def pause_connector(
    target: UUID, claims: Manager, repository: Repository, _: Idempotent
) -> None:
    await repository.action(claims, str(target), "pause")


@router.post("/{target}/resume", status_code=status.HTTP_204_NO_CONTENT)
async def resume_connector(
    target: UUID, claims: Manager, repository: Repository, _: Idempotent
) -> None:
    await repository.action(claims, str(target), "resume")


@router.get("/{target}/syncs", response_model=list[ConnectorSync])
async def list_syncs(target: UUID, claims: Viewer, repository: Repository) -> list[ConnectorSync]:
    return await repository.syncs(claims, str(target))
