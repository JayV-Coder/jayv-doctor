"""Criação de Organização e troca da Organização ativa.

As duas escritas passam por funções do banco: o `authenticated` não escreve em `tenants`,
`memberships` nem `user_active_tenant`. Depois delas o cliente renova a sessão para o JWT
trazer as claims novas.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from aid_api.auth import Claims, get_claims
from aid_api.db import tenant_tx
from aid_api.errors import ApiError

router = APIRouter(prefix="/api/v1/orgs", tags=["orgs"])

UNIQUE_VIOLATION = "23505"
INSUFFICIENT_PRIVILEGE = "42501"

SLUG_TAKEN = ApiError(409, "slug_taken", "Este identificador já está em uso.")
NOT_A_MEMBER = ApiError(403, "not_a_member", "Você não tem Vínculo com esta Organização.")


class NewOrganization(BaseModel):
    # `extra=forbid`: o payload nunca define tenant nem Papel.
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$")
    segment: str = Field(min_length=2, max_length=80)
    llm_provider: Literal["anthropic", "vertex"]
    dpa_accepted: Literal[True]


class CreatedOrganization(BaseModel):
    id: str


def sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


class OrganizationRepository:
    async def create(self, claims: Claims, organization: NewOrganization) -> str:
        try:
            async with tenant_tx(claims) as connection:
                result = await connection.execute(
                    text(
                        "select app.create_organization("
                        ":name, :slug, :segment, :llm_provider)::text"
                    ),
                    organization.model_dump(exclude={"dpa_accepted"}),
                )
                return str(result.scalar_one())
        except DBAPIError as exc:
            if sqlstate(exc) == UNIQUE_VIOLATION:
                raise SLUG_TAKEN from exc
            raise

    async def switch(self, claims: Claims, tenant_id: str) -> None:
        try:
            async with tenant_tx(claims) as connection:
                await connection.execute(
                    text("select app.switch_organization(cast(:tenant_id as uuid))"),
                    {"tenant_id": tenant_id},
                )
        except DBAPIError as exc:
            if sqlstate(exc) == INSUFFICIENT_PRIVILEGE:
                raise NOT_A_MEMBER from exc
            raise


def get_organization_repository() -> OrganizationRepository:
    return OrganizationRepository()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CreatedOrganization)
async def create_organization(
    organization: NewOrganization,
    claims: Annotated[Claims, Depends(get_claims)],
    repository: Annotated[OrganizationRepository, Depends(get_organization_repository)],
) -> CreatedOrganization:
    return CreatedOrganization(id=await repository.create(claims, organization))


@router.post("/{tenant_id}/switch", status_code=status.HTTP_204_NO_CONTENT)
async def switch_organization(
    tenant_id: UUID,
    claims: Annotated[Claims, Depends(get_claims)],
    repository: Annotated[OrganizationRepository, Depends(get_organization_repository)],
) -> None:
    await repository.switch(claims, str(tenant_id))
