"""Membros e Convites da Organização ativa.

O banco decide quem pode o quê, com o Papel lido da tabela: a claim pode estar atrasada. As
dependências daqui respondem antes com o erro certo, e `translate` cobre o que só o banco sabe.
"""

import asyncio
import hashlib
import os
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from aid_api.auth import Claims, get_claims, require_aal2_claims, require_role
from aid_api.db import tenant_tx
from aid_api.errors import ApiError
from aid_api.mailer import Mailer, get_mailer
from aid_api.orgs import sqlstate
from aid_api.permissions import MANAGE_MEMBERS

router = APIRouter(prefix="/api/v1", tags=["members"])

Role = Literal["owner", "admin", "analyst", "viewer"]
Deliver = Callable[[str, str], Awaitable[None]]


def last_owner() -> ApiError:
    return ApiError(409, "last_owner", "A Organização precisa de ao menos um Owner.")


ERRORS: dict[str, Callable[[], ApiError]] = {
    "DR001": last_owner,
    "DR002": lambda: ApiError(410, "invitation_gone", "Este convite expirou ou já foi usado."),
    "DR003": lambda: ApiError(
        403, "invitation_email_mismatch", "Este convite é de outro e-mail confirmado."
    ),
    "DR004": lambda: ApiError(409, "already_member", "Esta pessoa já é membro da Organização."),
    "23505": lambda: ApiError(
        409, "already_invited", "Já há um convite pendente para este e-mail."
    ),
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "P0002": lambda: ApiError(404, "not_found", "Registro não encontrado."),
}


def translate(state: str | None) -> ApiError | None:
    factory = ERRORS.get(state or "")
    return factory() if factory else None


class Member(BaseModel):
    id: str
    display_name: str | None
    email: str
    role: str
    mfa_enabled: bool


class Invitation(BaseModel):
    id: str
    email: str
    role: str
    expires_at: datetime


class NewInvitation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    role: Role


class RoleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role


# No corpo, não na URL como no ticket: caminho de requisição vai para os logs do Cloud Run.
class Acceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str


class CreatedInvitation(BaseModel):
    id: str


class AcceptedInvitation(BaseModel):
    tenant_id: str


@asynccontextmanager
async def transaction(claims: Claims) -> AsyncIterator[Callable[..., object]]:
    try:
        async with tenant_tx(claims) as connection:
            yield connection.execute
    except DBAPIError as exc:
        error = translate(sqlstate(exc))
        if error:
            raise error from exc
        raise


class MemberRepository:
    async def members(self, claims: Claims) -> list[Member]:
        async with transaction(claims) as execute:
            result = await execute(  # type: ignore[misc]
                text(
                    "select id::text, display_name, email, role, mfa_enabled"
                    " from doctor.list_members()"
                )
            )
            return [Member.model_validate(dict(row)) for row in result.mappings()]

    async def invitations(self, claims: Claims) -> list[Invitation]:
        async with transaction(claims) as execute:
            result = await execute(  # type: ignore[misc]
                text("select id::text, email, role, expires_at from doctor.list_invitations()")
            )
            return [Invitation.model_validate(dict(row)) for row in result.mappings()]

    async def invite(
        self, claims: Claims, email: str, role: str, token_hash: str
    ) -> tuple[str, str]:
        async with transaction(claims) as execute:
            result = await execute(  # type: ignore[misc]
                text("select id::text, organization from doctor.invite_member(:e, :r, :h)"),
                {"e": email, "r": role, "h": token_hash},
            )
            row = result.one()
            return row.id, row.organization

    # O e-mail sai dentro da transação: se falhar, o token antigo continua valendo.
    async def resend(self, claims: Claims, target: str, token_hash: str, deliver: Deliver) -> None:
        async with transaction(claims) as execute:
            result = await execute(  # type: ignore[misc]
                text(
                    "select email, organization from doctor.resend_invitation(cast(:t as uuid), :h)"
                ),
                {"t": target, "h": token_hash},
            )
            row = result.one()
            await deliver(row.email, row.organization)

    async def revoke(self, claims: Claims, target: str) -> None:
        async with transaction(claims) as execute:
            await execute(  # type: ignore[misc]
                text("select doctor.revoke_invitation(cast(:t as uuid))"), {"t": target}
            )

    async def accept(self, claims: Claims, token_hash: str) -> str:
        async with transaction(claims) as execute:
            result = await execute(  # type: ignore[misc]
                text("select doctor.accept_invitation(:h)::text"), {"h": token_hash}
            )
            return str(result.scalar_one())

    async def update_role(self, claims: Claims, target: str, role: str) -> None:
        async with transaction(claims) as execute:
            await execute(  # type: ignore[misc]
                text("select doctor.update_member_role(cast(:t as uuid), :r)"),
                {"t": target, "r": role},
            )

    async def remove(self, claims: Claims, target: str) -> None:
        async with transaction(claims) as execute:
            await execute(  # type: ignore[misc]
                text("select doctor.remove_member(cast(:t as uuid))"), {"t": target}
            )


def get_member_repository() -> MemberRepository:
    return MemberRepository()


def require_manager(
    claims: Annotated[Claims, Depends(require_role(*MANAGE_MEMBERS))],
) -> Claims:
    return require_aal2_claims(claims)


Manager = Annotated[Claims, Depends(require_manager)]
Repository = Annotated[MemberRepository, Depends(get_member_repository)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]


def new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# O token vai no fragmento, que o navegador não envia: fica fora dos logs do servidor web.
def invitation_url(token: str) -> str:
    base = os.environ.get("APP_URL", "http://127.0.0.1:3000")
    return f"{base}/convites/aceitar#{token}"


async def send(mailer: Mailer, email: str, organization: str, token: str) -> None:
    try:
        await asyncio.to_thread(mailer.send_invitation, email, organization, invitation_url(token))
    except OSError as exc:
        # O convite fica pendente e dá para reenviar pela tela.
        raise ApiError(503, "mail_unavailable", "Não foi possível enviar o e-mail.") from exc


@router.get("/memberships", response_model=list[Member])
async def list_memberships(claims: Manager, repository: Repository) -> list[Member]:
    return await repository.members(claims)


@router.patch("/memberships/{target}", status_code=status.HTTP_204_NO_CONTENT)
async def update_membership(
    target: UUID, change: RoleChange, claims: Manager, repository: Repository
) -> None:
    await repository.update_role(claims, str(target), change.role)


@router.delete("/memberships/{target}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_membership(target: UUID, claims: Manager, repository: Repository) -> None:
    await repository.remove(claims, str(target))


@router.get("/invitations", response_model=list[Invitation])
async def list_invitations(claims: Manager, repository: Repository) -> list[Invitation]:
    return await repository.invitations(claims)


@router.post("/invitations", status_code=status.HTTP_201_CREATED, response_model=CreatedInvitation)
async def create_invitation(
    invitation: NewInvitation, claims: Manager, repository: Repository, mailer: MailerDep
) -> CreatedInvitation:
    token, token_hash = new_token()
    created, organization = await repository.invite(
        claims, invitation.email, invitation.role, token_hash
    )
    await send(mailer, invitation.email, organization, token)
    return CreatedInvitation(id=created)


@router.post("/invitations/accept", response_model=AcceptedInvitation)
async def accept_invitation(
    acceptance: Acceptance,
    claims: Annotated[Claims, Depends(get_claims)],
    repository: Repository,
) -> AcceptedInvitation:
    tenant_id = await repository.accept(claims, hash_token(acceptance.token))
    return AcceptedInvitation(tenant_id=tenant_id)


@router.post("/invitations/{target}/resend", status_code=status.HTTP_204_NO_CONTENT)
async def resend_invitation(
    target: UUID, claims: Manager, repository: Repository, mailer: MailerDep
) -> None:
    token, token_hash = new_token()

    async def deliver(email: str, organization: str) -> None:
        await send(mailer, email, organization, token)

    await repository.resend(claims, str(target), token_hash, deliver)


@router.delete("/invitations/{target}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invitation(target: UUID, claims: Manager, repository: Repository) -> None:
    await repository.revoke(claims, str(target))
