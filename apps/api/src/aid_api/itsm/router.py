"""Chamados (ITSM, ticket #43, Tela 21). Todo Papel vê a conexão e os chamados; Owner e Admin
com MFA conectam e configuram o Jira; Analyst ou acima abre o chamado de um Incidente. O
webhook do Jira entra sem sessão e só pede a sincronização."""

import json
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from aid_api.core.auth import Claims, require_manager, require_role
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import MANAGE_CONNECTORS, VIEW
from aid_api.core.rate_limit import TokenBucketLimiter, check_rate, get_limiter, rate_limit
from aid_api.core.tokens import token_hash
from aid_api.itsm.repo import ItsmRepository, get_itsm_repository
from aid_api.itsm.schemas import (
    Authorization,
    Callback,
    JiraConfig,
    JiraConnection,
    ServiceNowConfig,
    ServiceNowConnection,
    ServiceNowSaved,
    Ticket,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["itsm"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)
# O evento do Jira traz a issue inteira; para achar a chave, 256 KB bastam.
HOOK_BYTES = 256 * 1024
hooks = APIRouter(prefix="/api/v1/itsm", tags=["itsm"])
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
    target: UUID,
    claims: Analyst,
    repository: Repository,
    _: Idempotent,
    provider: Literal["jira", "servicenow"] = "jira",
) -> list[Ticket]:
    """Abre o chamado no ITSM (uma vez por Incidente e provedor); a chave aparece quando o ITSM
    responde."""
    return await repository.request(claims, str(target), provider)


@router.get("/itsm/servicenow", response_model=ServiceNowConnection | None)
async def servicenow(claims: Viewer, repository: Repository) -> ServiceNowConnection | None:
    return await repository.servicenow(claims)


@router.put("/itsm/servicenow", response_model=ServiceNowSaved)
async def configure_servicenow(
    body: ServiceNowConfig, claims: Manager, repository: Repository, _: Idempotent
) -> ServiceNowSaved:
    """Instância, app OAuth (client credentials) e a regra de grupos. O endereço do webhook
    para a Business Rule volta só na primeira vez ou com `rotate_hook`."""
    return await repository.configure_servicenow(claims, body)


@router.delete("/itsm/servicenow", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_servicenow(claims: Manager, repository: Repository, _: Idempotent) -> None:
    await repository.disconnect_servicenow(claims)


async def head(request: Request) -> bytes:
    """Até 256 KB do corpo: evento maior só perde a chave (e relê todos os chamados abertos)."""
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > HOOK_BYTES:
            return b""
    return bytes(body)


def issue_key(body: bytes) -> str | None:
    """A chave da issue do evento (não confiável: o banco confere o formato e o `notifier`
    relê o chamado pela API do Jira)."""
    try:
        found = json.loads(body)
    except ValueError:
        return None
    issue = found.get("issue") if isinstance(found, dict) else None
    key = issue.get("key") if isinstance(issue, dict) else None
    return key[:40] if isinstance(key, str) else None


@hooks.post("/jira/hooks/{token}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def jira_hook(
    token: str,
    request: Request,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
) -> Response:
    # Sempre 204: o token errado não ganha resposta diferente.
    if 20 <= len(token) <= 100:
        check_rate(limiter, f"jira-hook:{token_hash(token)[:16]}")
        await repository.hook(token, issue_key(await head(request)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def incident_number(body: bytes) -> str | None:
    """O número do incident que a Business Rule manda: `{"number": "INC0010001"}`."""
    try:
        found = json.loads(body)
    except ValueError:
        return None
    number = found.get("number") if isinstance(found, dict) else None
    return number[:20] if isinstance(number, str) else None


@hooks.post(
    "/servicenow/hooks/{token}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False
)
async def servicenow_hook(
    token: str,
    request: Request,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
) -> Response:
    # Sempre 204, como o do Jira; o corpo só diz qual incident reler.
    if 20 <= len(token) <= 100:
        check_rate(limiter, f"servicenow-hook:{token_hash(token)[:16]}")
        await repository.servicenow_hook(token, incident_number(await head(request)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
