"""Rotas de Usuário, Organizações, Membros e Convites."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from aid_api.core.auth import Claims, get_claims, require_manager
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import MANAGE_MEMBERS
from aid_api.core.rate_limit import rate_limit
from aid_api.orgs import service
from aid_api.orgs.mailer import Mailer, get_mailer
from aid_api.orgs.repo import (
    MemberRepository,
    MeRepository,
    OrganizationRepository,
    get_me_repository,
    get_member_repository,
    get_organization_repository,
)
from aid_api.orgs.schemas import (
    Acceptance,
    AcceptedInvitation,
    CreatedInvitation,
    CreatedOrganization,
    Invitation,
    Me,
    Member,
    NewInvitation,
    NewOrganization,
    RoleChange,
)

router = APIRouter(
    prefix="/api/v1",
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)


CurrentClaims = Annotated[Claims, Depends(get_claims)]
Manager = Annotated[Claims, Depends(require_manager(*MANAGE_MEMBERS))]
Members = Annotated[MemberRepository, Depends(get_member_repository)]
Organizations = Annotated[OrganizationRepository, Depends(get_organization_repository)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]


@router.get("/me", response_model=Me, tags=["me"])
async def get_me(
    claims: CurrentClaims, repository: Annotated[MeRepository, Depends(get_me_repository)]
) -> Me:
    profile, organizations = await repository.me(claims)
    return Me(
        id=claims.sub,
        email=claims.email,
        aal=claims.aal,
        profile=profile,
        organizations=organizations,
        active_tenant_id=claims.tenant_id,
        active_role=claims.tenant_role,
    )


@router.post(
    "/orgs",
    status_code=status.HTTP_201_CREATED,
    response_model=CreatedOrganization,
    tags=["orgs"],
)
async def create_organization(
    organization: NewOrganization, claims: CurrentClaims, repository: Organizations, _: Idempotent
) -> CreatedOrganization:
    return CreatedOrganization(id=await repository.create(claims, organization))


@router.post("/orgs/{tenant_id}/switch", status_code=status.HTTP_204_NO_CONTENT, tags=["orgs"])
async def switch_organization(
    tenant_id: UUID, claims: CurrentClaims, repository: Organizations, _: Idempotent
) -> None:
    await repository.switch(claims, str(tenant_id))


@router.get("/memberships", response_model=list[Member], tags=["members"])
async def list_memberships(claims: Manager, repository: Members) -> list[Member]:
    return await repository.members(claims)


@router.patch("/memberships/{target}", status_code=status.HTTP_204_NO_CONTENT, tags=["members"])
async def update_membership(
    target: UUID, change: RoleChange, claims: Manager, repository: Members, _: Idempotent
) -> None:
    await repository.update_role(claims, str(target), change.role)


@router.delete("/memberships/{target}", status_code=status.HTTP_204_NO_CONTENT, tags=["members"])
async def delete_membership(
    target: UUID, claims: Manager, repository: Members, _: Idempotent
) -> None:
    await repository.remove(claims, str(target))


@router.get("/invitations", response_model=list[Invitation], tags=["members"])
async def list_invitations(claims: Manager, repository: Members) -> list[Invitation]:
    return await repository.invitations(claims)


@router.post(
    "/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=CreatedInvitation,
    tags=["members"],
)
async def create_invitation(
    invitation: NewInvitation,
    claims: Manager,
    repository: Members,
    mailer: MailerDep,
    _: Idempotent,
) -> CreatedInvitation:
    token, token_hash = service.new_token()
    created, organization = await repository.invite(
        claims, invitation.email, invitation.role, token_hash
    )
    await service.send_invitation(mailer, invitation.email, organization, token)
    return CreatedInvitation(id=created)


@router.post("/invitations/accept", response_model=AcceptedInvitation, tags=["members"])
async def accept_invitation(
    acceptance: Acceptance, claims: CurrentClaims, repository: Members, _: Idempotent
) -> AcceptedInvitation:
    tenant_id = await repository.accept(claims, service.hash_token(acceptance.token))
    return AcceptedInvitation(tenant_id=tenant_id)


@router.post(
    "/invitations/{target}/resend", status_code=status.HTTP_204_NO_CONTENT, tags=["members"]
)
async def resend_invitation(
    target: UUID, claims: Manager, repository: Members, mailer: MailerDep, _: Idempotent
) -> None:
    token, token_hash = service.new_token()

    async def deliver(email: str, organization: str) -> None:
        await service.send_invitation(mailer, email, organization, token)

    await repository.resend(claims, str(target), token_hash, deliver)


@router.delete("/invitations/{target}", status_code=status.HTTP_204_NO_CONTENT, tags=["members"])
async def delete_invitation(
    target: UUID, claims: Manager, repository: Members, _: Idempotent
) -> None:
    await repository.revoke(claims, str(target))
