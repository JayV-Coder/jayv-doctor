"""Tokens de ingestão (Owner e Admin com MFA) e POST /ingestion/events (sistemas externos)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status

from aid_api.core.auth import Claims, require_aal2_claims, require_role
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import MANAGE_CONNECTORS
from aid_api.core.rate_limit import TokenBucketLimiter, check_rate, get_limiter, rate_limit
from aid_api.ingestion import service
from aid_api.ingestion.repo import IngestionRepository, get_ingestion_repository, invalid_token
from aid_api.ingestion.schemas import (
    CreatedIngestionToken,
    IngestionResult,
    IngestionToken,
    NewIngestionToken,
)

Repository = Annotated[IngestionRepository, Depends(get_ingestion_repository)]


def require_manager(
    claims: Annotated[Claims, Depends(require_role(*MANAGE_CONNECTORS))],
) -> Claims:
    return require_aal2_claims(claims)


Manager = Annotated[Claims, Depends(require_manager)]

tokens = APIRouter(
    prefix="/api/v1/ingestion-tokens",
    tags=["ingestion"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)


@tokens.get("", response_model=list[IngestionToken])
async def list_tokens(claims: Manager, repository: Repository) -> list[IngestionToken]:
    return await repository.tokens(claims)


@tokens.post("", status_code=status.HTTP_201_CREATED, response_model=CreatedIngestionToken)
async def create_token(
    new: NewIngestionToken, claims: Manager, repository: Repository, _: Idempotent
) -> CreatedIngestionToken:
    token, token_hash, prefix = service.new_token()
    created = await repository.create_token(
        claims, new.name, str(new.integration_id), token_hash, prefix
    )
    return CreatedIngestionToken(id=created, token=token, prefix=prefix)


@tokens.post("/{target}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    target: UUID, claims: Manager, repository: Repository, _: Idempotent
) -> None:
    await repository.revoke_token(claims, str(target))


events = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])

EVENTS_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["events"],
                    "properties": {
                        "events": {
                            "type": "array",
                            "maxItems": service.MAX_EVENTS,
                            # O schema completo é o Contrato de evento v1, em
                            # packages/contracts/schemas/event.v1.json.
                            "items": {
                                "type": "object",
                                "description": "Evento no Contrato de evento v1, sem tenant_id",
                            },
                        }
                    },
                }
            }
        },
    }
}


async def read_limited(request: Request) -> bytes:
    """O corpo, sem passar de 1 MB na memória: recusa pelo Content-Length ou no meio da leitura."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > service.MAX_BYTES:
        raise service.too_large()
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > service.MAX_BYTES:
            raise service.too_large()
    return bytes(body)


# Sem JWT de Usuário: quem chama é um sistema externo, com `Authorization: Bearer aid_ing_…`.
@events.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionResult,
    openapi_extra=EVENTS_BODY,
)
async def ingest_events(
    request: Request,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
    authorization: Annotated[str | None, Header()] = None,
) -> IngestionResult:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.startswith(service.INGESTION_PREFIX):
        raise invalid_token()
    token_hash = service.hash_token(token)
    # Token conferido antes de ler o corpo e de gastar balde do rate limit: chamada com token
    # inventado não faz a API guardar 1 MB nem expulsa os baldes de quem é de verdade.
    identity = await repository.identify(token_hash)
    check_rate(limiter, f"ingestion:{identity.token_id}")
    batch = service.parse_batch(await read_limited(request))
    accepted, rejected = service.split(batch, identity.integration_id)
    if accepted:
        await repository.accept(token_hash, accepted)
    return IngestionResult(accepted=len(accepted), rejected=rejected)
