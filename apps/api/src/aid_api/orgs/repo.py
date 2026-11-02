"""Acesso a dados de Organizações, Membros e Convites, sempre dentro de `tenant_tx`.

As escritas passam por funções do banco: o `authenticated` não escreve nessas tabelas, e é lá que
o Papel é lido da tabela, porque a claim pode estar atrasada.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aid_api.core.auth import Claims
from aid_api.core.db import tenant_tx, translated_tx
from aid_api.core.errors import ApiError
from aid_api.orgs.schemas import Invitation, Member, NewOrganization, Organization, Profile

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


def slug_taken() -> ApiError:
    return ApiError(409, "slug_taken", "Este identificador já está em uso.")


def not_a_member() -> ApiError:
    return ApiError(403, "not_a_member", "Você não tem Vínculo com esta Organização.")


@asynccontextmanager
async def transaction(
    claims: Claims, overrides: dict[str, Callable[[], ApiError]] | None = None
) -> AsyncIterator[AsyncConnection]:
    """`tenant_tx` que traduz o erro do banco em erro da API; `overrides` vale por rota."""
    async with translated_tx(claims, {**ERRORS, **(overrides or {})}) as connection:
        yield connection


class MeRepository:
    async def me(self, claims: Claims) -> tuple[Profile | None, list[Organization]]:
        async with tenant_tx(claims) as connection:
            result = await connection.execute(
                text(
                    "select display_name as full_name, avatar_url, 'pt-BR' as locale"
                    " from public.profiles where user_id = auth.uid()"
                )
            )
            row = result.mappings().first()
            organizations = await connection.execute(
                text(
                    "select id::text, name, slug, role"
                    " from doctor.list_organizations() order by name"
                )
            )
            return (
                Profile.model_validate(dict(row)) if row else None,
                [Organization.model_validate(dict(item)) for item in organizations.mappings()],
            )


class OrganizationRepository:
    async def create(self, claims: Claims, organization: NewOrganization) -> str:
        async with transaction(claims, {"23505": slug_taken}) as connection:
            result = await connection.execute(
                text(
                    "select doctor.create_organization(:name, :slug, :segment, :llm_provider)::text"
                ),
                organization.model_dump(exclude={"dpa_accepted"}),
            )
            return str(result.scalar_one())

    async def switch(self, claims: Claims, tenant_id: str) -> None:
        async with transaction(claims, {"42501": not_a_member}) as connection:
            await connection.execute(
                text("select doctor.switch_organization(cast(:tenant_id as uuid))"),
                {"tenant_id": tenant_id},
            )


class MemberRepository:
    async def members(self, claims: Claims) -> list[Member]:
        async with transaction(claims) as connection:
            result = await connection.execute(
                text(
                    "select id::text, display_name, email, role, mfa_enabled"
                    " from doctor.list_members()"
                )
            )
            return [Member.model_validate(dict(row)) for row in result.mappings()]

    async def invitations(self, claims: Claims) -> list[Invitation]:
        async with transaction(claims) as connection:
            result = await connection.execute(
                text("select id::text, email, role, expires_at from doctor.list_invitations()")
            )
            return [Invitation.model_validate(dict(row)) for row in result.mappings()]

    async def invite(
        self, claims: Claims, email: str, role: str, token_hash: str
    ) -> tuple[str, str]:
        async with transaction(claims) as connection:
            result = await connection.execute(
                text("select id::text, organization from doctor.invite_member(:e, :r, :h)"),
                {"e": email, "r": role, "h": token_hash},
            )
            row = result.one()
            return row.id, row.organization

    # O e-mail sai dentro da transação: se falhar, o token antigo continua valendo.
    async def resend(self, claims: Claims, target: str, token_hash: str, deliver: Deliver) -> None:
        async with transaction(claims) as connection:
            result = await connection.execute(
                text(
                    "select email, organization from doctor.resend_invitation(cast(:t as uuid), :h)"
                ),
                {"t": target, "h": token_hash},
            )
            row = result.one()
            await deliver(row.email, row.organization)

    async def revoke(self, claims: Claims, target: str) -> None:
        async with transaction(claims) as connection:
            await connection.execute(
                text("select doctor.revoke_invitation(cast(:t as uuid))"), {"t": target}
            )

    async def accept(self, claims: Claims, token_hash: str) -> str:
        async with transaction(claims) as connection:
            result = await connection.execute(
                text("select doctor.accept_invitation(:h)::text"), {"h": token_hash}
            )
            return str(result.scalar_one())

    async def update_role(self, claims: Claims, target: str, role: str) -> None:
        async with transaction(claims) as connection:
            await connection.execute(
                text("select doctor.update_member_role(cast(:t as uuid), :r)"),
                {"t": target, "r": role},
            )

    async def remove(self, claims: Claims, target: str) -> None:
        async with transaction(claims) as connection:
            await connection.execute(
                text("select doctor.remove_member(cast(:t as uuid))"), {"t": target}
            )


def get_me_repository() -> MeRepository:
    return MeRepository()


def get_organization_repository() -> OrganizationRepository:
    return OrganizationRepository()


def get_member_repository() -> MemberRepository:
    return MemberRepository()
