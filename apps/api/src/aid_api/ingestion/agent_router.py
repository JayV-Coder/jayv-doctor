"""Rotas do agente local (ticket #39). Sem sessão de Usuário: o agente prova quem é com o
segredo e a assinatura de cada requisição (`aid_api.ingestion.agent`). Só chamadas de saída do
agente: nada aqui abre conexão para dentro da rede do cliente."""

import asyncio
import time
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import ValidationError

from aid_api.core.errors import ApiError
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
    AgentLlmRequest,
    AgentLlmResult,
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
# O modelo local está esperando: o pedido sai em até 1 s.
LLM_POLL_STEP = 1.0
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
    # O lote de Eventos e a resposta do modelo local têm corpo de verdade.
    large = request.url.path.endswith("/events") or "/llm/" in request.url.path
    limit = service.MAX_BYTES if large else SMALL_BODY
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


@agent.get(
    "/llm",
    response_model=AgentLlmRequest,
    responses={204: {"description": "sem pedido"}},
)
async def llm_next(identity: Agent, repository: Repository) -> Any:
    """Long-poll do próximo pedido ao modelo local (#46, ADR-0019): o agente leva o prompt ao
    servidor da rede do cliente e devolve a resposta em `POST /llm/{id}`."""
    deadline = time.monotonic() + LONG_POLL_SECONDS
    while True:
        found = await repository.claim_llm(identity.secret_hash)
        if found is not None:
            return AgentLlmRequest(id=found[0], request=found[1], timeout_seconds=found[2])
        if time.monotonic() + LLM_POLL_STEP >= deadline:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        await asyncio.sleep(LLM_POLL_STEP)


# Fora do schema público, como os webhooks de ITSM: autenticada pelo agente, não pelo JWT da
# Organização (o isolamento entre agentes é do banco: `finish_local_llm` só aceita o próprio).
@agent.post("/llm/{target}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def llm_result(
    target: UUID, request: Request, identity: Agent, repository: Repository
) -> Response:
    try:
        body = AgentLlmResult.model_validate_json(request.state.body or b"{}")
    except ValidationError as exc:
        raise ApiError(422, "validation_error", "Resposta do modelo local inválida.") from exc
    if (body.response is None) == (body.error is None):
        raise ApiError(422, "validation_error", "Mande a resposta ou o erro.")
    if not await repository.finish_llm(
        identity.secret_hash, str(target), body.response, body.error
    ):
        raise ApiError(404, "not_found", "Pedido não encontrado ou já respondido.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
