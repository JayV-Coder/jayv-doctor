"""Chamados (ITSM, ticket #43, Tela 21). Todo Papel vê a conexão e os chamados; Owner e Admin
com MFA conectam e configuram o Jira; Analyst ou acima abre o chamado de um Incidente. O
webhook do Jira entra sem sessão e só pede a sincronização."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from aid_api.core.auth import Claims, require_manager, require_role
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import MANAGE_CONNECTORS, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.itsm.repo import ItsmRepository, get_itsm_repository
from aid_api.itsm.schemas import Authorization, Callback, JiraConfig, JiraConnection, Ticket

router = APIRouter(
    prefix="/api/v1",
    tags=["itsm"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)
hooks = APIRouter(prefix="/api/v1/itsm/jira/hooks", tags=["itsm"])
Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Analyst = Annotated[Claims, Depends(require_role("owner", "admin", "analyst"))]
Manager = Annotated[Claims, Depends(require_manager(*MANAGE_CONNECTORS))]
Repository = Annotated[ItsmRepository, Depends(get_itsm_repository)]


@router.get("/itsm/jira", response_model=JiraConnection | None)
async def connection(claims: Viewer, repository: Repository) -> JiraConnection | None:
    return await repository.connection(claims)


@router.post("/itsm/jira/authorize", response_model=Authorization)
async def authorize(claims: Manager, repository: Repository) -> Authorization:
    """URL do consentimento no Atlassian, com o `state` de uso único (10 min)."""
    return await repository.authorize(claims)


@router.post("/itsm/jira/callback", response_model=JiraConnection | None)
async def callback(
    body: Callback, claims: Manager, repository: Repository
) -> JiraConnection | None:
    return await repository.callback(claims, body.code, body.state)


@router.put("/itsm/jira", response_model=JiraConnection | None)
async def configure(
    body: JiraConfig, claims: Manager, repository: Repository, _: Idempotent
) -> JiraConnection | None:
    return await repository.configure(claims, body)


@router.delete("/itsm/jira", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(claims: Manager, repository: Repository, _: Idempotent) -> None:
    await repository.disconnect(claims)


@router.get("/incidents/{target}/tickets", response_model=list[Ticket])
async def tickets(target: UUID, claims: Viewer, repository: Repository) -> list[Ticket]:
    return await repository.tickets(claims, str(target))


@router.post(
    "/incidents/{target}/tickets",
    response_model=list[Ticket],
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_ticket(
    target: UUID, claims: Analyst, repository: Repository, _: Idempotent
) -> list[Ticket]:
    """Abre o chamado no Jira (uma vez por Incidente); a chave aparece quando o Jira responde."""
    return await repository.request(claims, str(target))


@hooks.post("/{token}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def jira_hook(token: str, repository: Repository) -> Response:
    # Sempre 204: o token errado não ganha resposta diferente.
    if 20 <= len(token) <= 100:
        await repository.hook(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
