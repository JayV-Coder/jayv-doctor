"""Políticas avançadas da Organização (ticket #49): MFA obrigatório para todos os Papéis."""

from typing import Annotated

from fastapi import APIRouter, Depends

from aid_api.core.auth import Claims, require_manager
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.rate_limit import rate_limit
from aid_api.policies.repo import PolicyRepository, get_policy_repository
from aid_api.policies.schemas import Policies

router = APIRouter(
    prefix="/api/v1",
    tags=["policies"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)
Manager = Annotated[Claims, Depends(require_manager("owner", "admin"))]
Repository = Annotated[PolicyRepository, Depends(get_policy_repository)]


@router.get("/policies", response_model=Policies)
async def get_policies(claims: Manager, repository: Repository) -> Policies:
    return await repository.get(claims)


@router.put("/policies", response_model=Policies)
async def update_policies(
    policies: Policies, claims: Manager, repository: Repository, _: Idempotent
) -> Policies:
    return await repository.update(claims, policies)
