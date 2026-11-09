"""Agentes locais (ticket #39): Owner ou Admin com MFA criam, configuram, revogam e rotacionam;
todo Papel vê o status, a versão e quando cada agente falou pela última vez (Tela de agentes)."""

import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from aid_api.agents.config import validate
from aid_api.agents.repo import AgentRepository, get_agents_repository
from aid_api.agents.schemas import Agent, AgentConfigChange, NewAgent, RegistrationToken
from aid_api.core.auth import Claims, require_manager, require_role
from aid_api.core.permissions import MANAGE_CONNECTORS, VIEW
from aid_api.core.rate_limit import rate_limit

router = APIRouter(prefix="/api/v1/agents", tags=["agents"], dependencies=[Depends(rate_limit)])
Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Manager = Annotated[Claims, Depends(require_manager(*MANAGE_CONNECTORS))]
Repository = Annotated[AgentRepository, Depends(get_agents_repository)]
TOKEN_HOURS = 24
IMAGE = "ghcr.io/jayv-coder/aid-agent:latest"


def install_command(request: Request, token: str) -> str:
    """O comando que o cliente roda na máquina do agente: só a URL pública da API e o token."""
    api = os.environ.get("AID_PUBLIC_API_URL") or str(request.base_url).rstrip("/")
    # O registro roda uma vez (--rm); o agente em si sobe depois, com reinício automático.
    return (
        f"docker run --rm -v aid-agent:/var/lib/aid-agent {IMAGE} register --api {api}"
        f" --token {token} && docker run -d --name aid-agent --restart unless-stopped"
        f" -v aid-agent:/var/lib/aid-agent {IMAGE} run"
    )


@router.get("", response_model=list[Agent])
async def list_agents(claims: Viewer, repository: Repository) -> list[Agent]:
    return await repository.list(claims)


@router.post("", response_model=RegistrationToken, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: NewAgent, request: Request, claims: Manager, repository: Repository
) -> RegistrationToken:
    agent_id, token = await repository.create(
        claims, body.name, str(body.integration_id), validate(body.config)
    )
    return RegistrationToken(
        id=agent_id,
        registration_token=token,
        expires_in_hours=TOKEN_HOURS,
        install_command=install_command(request, token),
    )


@router.patch("/{target}", response_model=dict[str, int])
async def change_config(
    target: UUID, body: AgentConfigChange, claims: Manager, repository: Repository
) -> dict[str, int]:
    return {
        "config_version": await repository.change_config(claims, str(target), validate(body.config))
    }


@router.post("/{target}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_agent(target: UUID, claims: Manager, repository: Repository) -> None:
    await repository.revoke(claims, str(target))


@router.post("/{target}/rotate", response_model=RegistrationToken)
async def rotate_agent(
    target: UUID, request: Request, claims: Manager, repository: Repository
) -> RegistrationToken:
    token = await repository.rotate(claims, str(target))
    return RegistrationToken(
        id=str(target),
        registration_token=token,
        expires_in_hours=TOKEN_HOURS,
        install_command=install_command(request, token),
    )
