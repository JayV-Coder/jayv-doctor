"""Rota do Dashboard executivo (ticket #21). Todo Papel lê."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from aid_api.core.auth import Claims, require_role
from aid_api.core.permissions import VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.dashboard.repo import DashboardRepository, get_dashboard_repository
from aid_api.dashboard.schemas import Dashboard, Period

router = APIRouter(prefix="/api/v1", tags=["dashboard"], dependencies=[Depends(rate_limit)])

Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Repository = Annotated[DashboardRepository, Depends(get_dashboard_repository)]


@router.get("/dashboard", response_model=Dashboard)
async def dashboard(
    claims: Viewer,
    repository: Repository,
    period: Period = "24h",
    environment: Literal["prd", "hml", "dev"] | None = None,
    integration_id: UUID | None = None,
) -> Dashboard:
    return await repository.load(claims, period, environment, integration_id, datetime.now(UTC))
