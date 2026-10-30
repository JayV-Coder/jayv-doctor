"""`GET /api/v1/me`: quem é o Usuário e em qual Organização está agindo."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from aid_api.auth import Claims, get_claims
from aid_api.db import tenant_tx

router = APIRouter(prefix="/api/v1", tags=["me"])


class Profile(BaseModel):
    full_name: str | None
    avatar_url: str | None
    locale: str


class Organization(BaseModel):
    id: str
    name: str
    slug: str
    role: str


class Me(BaseModel):
    id: str
    email: str | None
    aal: str | None
    profile: Profile | None
    organizations: list[Organization]
    active_tenant_id: str | None
    active_role: str | None


class MeRepository:
    async def profile(self, claims: Claims) -> Profile | None:
        async with tenant_tx(claims) as connection:
            result = await connection.execute(
                text("select full_name, avatar_url, locale from public.profiles")
            )
            row = result.mappings().first()
        return Profile.model_validate(dict(row)) if row else None

    async def organizations(self, claims: Claims) -> list[Organization]:
        async with tenant_tx(claims) as connection:
            result = await connection.execute(
                text(
                    "select id::text, name, slug, role from app.list_organizations() order by name"
                )
            )
            return [Organization.model_validate(dict(row)) for row in result.mappings()]


def get_me_repository() -> MeRepository:
    return MeRepository()


@router.get("/me", response_model=Me)
async def get_me(
    claims: Annotated[Claims, Depends(get_claims)],
    repository: Annotated[MeRepository, Depends(get_me_repository)],
) -> Me:
    return Me(
        id=claims.sub,
        email=claims.email,
        aal=claims.aal,
        profile=await repository.profile(claims),
        organizations=await repository.organizations(claims),
        active_tenant_id=claims.tenant_id,
        active_role=claims.tenant_role,
    )
