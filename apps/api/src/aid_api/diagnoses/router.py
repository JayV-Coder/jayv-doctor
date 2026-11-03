"""Rotas do Diagnóstico (ticket #24). Pedir é assíncrono: `202` com o Diagnóstico na fila, e o
progresso (`stage`) chega pelo Realtime (ADR-0005). Todo Papel lê; Analyst ou acima pede; Owner
ou Admin liga o Diagnóstico automático de Incidente crítico."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, status

from aid_api.core.auth import Claims, require_role
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import CONFIGURE_DIAGNOSIS, OPERATE, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.diagnoses.repo import DiagnosisRepository, get_diagnosis_repository
from aid_api.diagnoses.schemas import (
    DiagnosisDetail,
    DiagnosisQueued,
    DiagnosisRequest,
    DiagnosisSettings,
    DiagnosisSummary,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["diagnoses"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)

Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Operator = Annotated[Claims, Depends(require_role(*OPERATE))]
Manager = Annotated[Claims, Depends(require_role(*CONFIGURE_DIAGNOSIS))]
Repository = Annotated[DiagnosisRepository, Depends(get_diagnosis_repository)]


@router.post(
    "/incidents/{incident}/diagnoses",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DiagnosisQueued,
)
async def request_diagnosis(
    incident: UUID,
    body: DiagnosisRequest,
    claims: Operator,
    repository: Repository,
    _: Idempotent,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=255)] = None,
) -> DiagnosisQueued:
    # A mesma chave é o mesmo Diagnóstico também no banco (`processing_key`), não só na resposta.
    key = f"req:{idempotency_key}" if idempotency_key else f"req:{uuid4()}"
    return await repository.request(claims, str(incident), body, key)


@router.get("/incidents/{incident}/diagnoses", response_model=list[DiagnosisSummary])
async def list_diagnoses(
    incident: UUID, claims: Viewer, repository: Repository
) -> list[DiagnosisSummary]:
    return await repository.for_incident(claims, str(incident))


@router.get("/diagnoses/{target}", response_model=DiagnosisDetail)
async def get_diagnosis(target: UUID, claims: Viewer, repository: Repository) -> DiagnosisDetail:
    return await repository.detail(claims, str(target))


@router.get("/settings/diagnosis", response_model=DiagnosisSettings)
async def get_settings(claims: Viewer, repository: Repository) -> DiagnosisSettings:
    return await repository.settings(claims)


@router.put("/settings/diagnosis", response_model=DiagnosisSettings)
async def put_settings(
    new: DiagnosisSettings, claims: Manager, repository: Repository, _: Idempotent
) -> DiagnosisSettings:
    return await repository.update_settings(claims, new)
