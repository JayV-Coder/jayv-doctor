"""Rotas do agente local (ticket #39). Sem sessão de Usuário: o agente prova quem é com o
segredo e a assinatura de cada requisição (`aid_api.ingestion.agent`). Só chamadas de saída do
agente: nada aqui abre conexão para dentro da rede do cliente."""

import asyncio
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response, status

from aid_api.core.rate_limit import TokenBucketLimiter, check_rate, get_limiter
from aid_api.ingestion import service
from aid_api.ingestion.agent import (
    SECRET_PREFIX,
    AgentIdentity,
    AgentRepository,
    get_agent_repository,
    release,
    secret_hash,
    signed_target,
    unauthorized,
    verify,
)
from aid_api.ingestion.schemas import (
    AgentConfig,
    AgentRegistered,
    AgentRegistration,
    AgentUpdate,
    IngestionResult,
)

agent = APIRouter(prefix="/api/v1/agent", tags=["agent"])
Repository = Annotated[AgentRepository, Depends(get_agent_repository)]
# Long-poll da config: responde na hora se mudou, senão espera até 25 s (abaixo dos 30 s comuns
# de proxy na rede do cliente), olhando o banco a cada 5 s.
LONG_POLL_SECONDS = 25.0
POLL_STEP = 5.0
# Só `/events` tem corpo de verdade; as outras rotas assinam um corpo vazio.
SMALL_BODY = 4096


async def authenticated(
    request: Request,
    repository: Repository,
    authorization: Annotated[str | None, Header()] = None,
    x_aid_timestamp: Annotated[str | None, Header()] = None,
    x_aid_signature: Annotated[str | None, Header()] = None,
) -> AgentIdentity:
    scheme, _, secret = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secret.startswith(SECRET_PREFIX):
        raise unauthorized()
    if not x_aid_timestamp or not x_aid_signature:
        raise unauthorized()
    identity = await repository.identify(secret_hash(secret))
    # O corpo é lido com o mesmo teto da ingestão por API, sem passar dele na memória, e fica
    # guardado para a rota.
    limit = service.MAX_BYTES if request.url.path.endswith("/events") else SMALL_BODY
    body = await service.read_limited(request, limit)
    request.state.body = body
    verify(
        identity.public_key,
        request.method,
        signed_target(request.url.path, request.url.query),
        x_aid_timestamp,
        x_aid_signature,
        body,
    )
    return identity


Agent = Annotated[AgentIdentity, Depends(authenticated)]


@agent.post("/register", response_model=AgentRegistered, status_code=status.HTTP_201_CREATED)
async def register(body: AgentRegistration, repository: Repository) -> AgentRegistered:
    """Token de uso único (criado na tela) mais a chave pública que o agente gerou. Devolve o
    segredo do agente, que não aparece de novo, e o certificado do mTLS."""
    agent_id, secret, certificate = await repository.register(
        body.token, body.public_key, body.version
    )
    return AgentRegistered(agent_id=agent_id, secret=secret, certificate=certificate)


@agent.get("/config", response_model=AgentConfig, responses={304: {"description": "sem mudança"}})
async def config(
    identity: Agent, repository: Repository, known_version: int = 0, version: str = ""
) -> Any:
    """Long-poll da config, que também é o sinal de vida do agente (`version` na query)."""
    await repository.seen(identity.secret_hash, version[:40] or "desconhecida")
    deadline = time.monotonic() + LONG_POLL_SECONDS
    current = identity
    while current.config_version == known_version and time.monotonic() < deadline:
        await asyncio.sleep(POLL_STEP)
        current = await repository.identify(identity.secret_hash)
    if current.config_version == known_version:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)
    manifest = release()
    return AgentConfig(
        integration_id=current.integration_id,
        config=current.config,
        config_version=current.config_version,
        update=AgentUpdate.model_validate(manifest) if manifest else None,
    )


@agent.post("/events", status_code=status.HTTP_202_ACCEPTED, response_model=IngestionResult)
async def events(
    request: Request,
    identity: Agent,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
) -> IngestionResult:
    """O mesmo contrato e os mesmos limites do POST /ingestion/events, com o tenant e a
    Integração vindos do agente."""
    check_rate(limiter, f"agent:{identity.agent_id}")
    batch = service.parse_batch(request.state.body)
    accepted, rejected = service.split(batch, identity.integration_id)
    if accepted:
        await repository.accept(identity.secret_hash, accepted)
    return IngestionResult(accepted=len(accepted), rejected=rejected)
