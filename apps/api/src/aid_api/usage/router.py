"""Uso e Cotas (ticket #31): todo Papel vê o consumo da Organização ativa (Tela 17)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from aid_api.core.auth import Claims, require_role
from aid_api.core.permissions import VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.usage.repo import UsageRepository, get_usage_repository
from aid_api.usage.schemas import Usage

router = APIRouter(prefix="/api/v1", tags=["usage"], dependencies=[Depends(rate_limit)])

Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Repository = Annotated[UsageRepository, Depends(get_usage_repository)]


@router.get("/usage", response_model=Usage)
async def get_usage(claims: Viewer, repository: Repository) -> Usage:
    return await repository.usage(claims)
