"""Rotas de retenção e LGPD (ticket #29). Todo Papel vê as políticas; Owner ou Admin com MFA as
mudam, desligam o envio ao LLM e atendem o titular; só o Owner pede a exclusão total."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from aid_api.core.auth import Claims, require_manager, require_role
from aid_api.core.errors import ApiError
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import GOVERN, MANAGE_PRIVACY, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.core.references import reference_of
from aid_api.privacy.repo import PrivacyRepository, get_privacy_repository
from aid_api.privacy.schemas import (
    AiProfileChange,
    DeletionRequest,
    LlmChange,
    PrivacySettings,
    RetentionChange,
    SubjectErased,
    SubjectEvents,
    SubjectQuery,
)

router = APIRouter(
    prefix="/api/v1/privacy",
    tags=["privacy"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)

Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Manager = Annotated[Claims, Depends(require_manager(*MANAGE_PRIVACY))]
Owner = Annotated[Claims, Depends(require_manager(*GOVERN))]
Repository = Annotated[PrivacyRepository, Depends(get_privacy_repository)]


def subject_reference(claims: Claims, query: SubjectQuery) -> str:
    reference = reference_of(claims, query.reference)
    if reference is None:
        raise ApiError(503, "hmac_unavailable", "A chave das Referências não está configurada.")
    return reference


@router.get("", response_model=PrivacySettings)
async def get_privacy(claims: Viewer, repository: Repository) -> PrivacySettings:
    return await repository.settings(claims)


@router.put("/retention", status_code=status.HTTP_204_NO_CONTENT)
async def put_retention(
    change: RetentionChange, claims: Manager, repository: Repository, _: Idempotent
) -> Response:
    await repository.set_retention(claims, change)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/ai-profile", status_code=status.HTTP_204_NO_CONTENT)
async def put_ai_profile(
    change: AiProfileChange, claims: Manager, repository: Repository, _: Idempotent
) -> Response:
    """Perfil de IA (ADR-0018): Owner com MFA troca entre o padrão e o Brasil."""
    await repository.set_ai_profile(claims, change.profile)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/llm", status_code=status.HTTP_204_NO_CONTENT)
async def put_llm(
    change: LlmChange, claims: Manager, repository: Repository, _: Idempotent
) -> Response:
    await repository.set_llm(claims, change.enabled)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/deletion", status_code=status.HTTP_202_ACCEPTED, response_model=PrivacySettings)
async def request_deletion(
    request: DeletionRequest, claims: Owner, repository: Repository, _: Idempotent
) -> PrivacySettings:
    """Agenda a exclusão total para daqui a 7 dias (cancelável até lá)."""
    await repository.request_deletion(claims, request)
    return await repository.settings(claims)


@router.delete("/deletion", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_deletion(claims: Owner, repository: Repository, _: Idempotent) -> Response:
    await repository.cancel_deletion(claims)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/subject/search", response_model=SubjectEvents)
async def find_subject(
    query: SubjectQuery, claims: Manager, repository: Repository
) -> SubjectEvents:
    return await repository.find_subject(claims, subject_reference(claims, query))


@router.post("/subject/erase", response_model=SubjectErased)
async def erase_subject(
    query: SubjectQuery, claims: Manager, repository: Repository, _: Idempotent
) -> SubjectErased:
    return SubjectErased(
        events_erased=await repository.erase_subject(claims, subject_reference(claims, query))
    )
