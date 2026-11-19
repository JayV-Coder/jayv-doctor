"""Acesso a dados de Organizações, Membros e Convites, sempre dentro de `tenant_tx`.

As escritas passam por funções do banco: o `authenticated` não escreve nessas tabelas, e é lá que
o Papel é lido da tabela, porque a claim pode estar atrasada.
"""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.orgs.schemas import (
    AvailableOrganization,
    EnabledOrganization,
    Invitation,
    MeData,
    Member,
    NewOrganization,
    Organization,
    Profile,
)

Deliver = Callable[[str, str], Awaitable[None]]
logger = logging.getLogger(__name__)


def last_owner() -> ApiError:
    return ApiError(409, "last_owner", "A Organização precisa de ao menos um Owner.")


ERRORS: dict[str, Callable[[], ApiError]] = {
    "DR001": last_owner,
    "DR002": lambda: ApiError(410, "invitation_gone", "Este convite expirou ou já foi usado."),
    "DR003": lambda: ApiError(
        403, "invitation_email_mismatch", "Este convite é de outro e-mail confirmado."
    ),
    "DR004": lambda: ApiError(409, "already_member", "Esta pessoa já é membro da Organização."),
    "DR051": lambda: ApiError(
        409, "plan_limit", "O plano da Organização chegou ao limite de membros (com os convites)."
    ),
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
    # 404 como todo recurso de outra Organização (#27): a resposta é a mesma se ela nem existe.
    return ApiError(404, "not_a_member", "Você não tem Vínculo com esta Organização.")


def not_owner() -> ApiError:
    return ApiError(403, "not_owner", "Só o owner da Organização ativa o Doctor.")


def already_enabled() -> ApiError:
    return ApiError(409, "already_enabled", "O Doctor já está ativo nesta Organização.")


@asynccontextmanager
async def transaction(
    claims: Claims,
    overrides: dict[str, Callable[[], ApiError]] | None = None,
    *,
    check_access: bool = True,
) -> AsyncIterator[AsyncConnection]:
    """`tenant_tx` que traduz o erro do banco em erro da API; `overrides` vale por rota."""
    async with translated_tx(
        claims, {**ERRORS, **(overrides or {})}, check_access=check_access
    ) as connection:
        yield connection


class MeRepository:
    JOIN = "select doctor.join_organizations()"

    async def me(self, claims: Claims) -> MeData:
        """Antes de listar, dá o Vínculo que falta nas Organizações do jayv-coder em que o
        Doctor está ativo (ADR-0025). Num savepoint: se falhar, o /me responde com o que há.
        Sem conferir o acesso: o /me responde também sem o MFA que a Organização exige (#49)."""
        async with transaction(claims, check_access=False) as connection:
            try:
                async with connection.begin_nested():
                    await connection.execute(text(self.JOIN))
            except DBAPIError:
                logger.warning("acesso automático às Organizações falhou", exc_info=True)
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
            available = await connection.execute(
                text(
                    "select id::text, name, slug, coder_role from doctor.available_organizations()"
                )
            )
            mfa_required = await connection.scalar(
                text("select doctor.access_problem() is not distinct from 'mfa_required'")
            )
            return MeData(
                profile=Profile.model_validate(dict(row)) if row else None,
                organizations=[
                    Organization.model_validate(dict(item)) for item in organizations.mappings()
                ],
                available=[
                    AvailableOrganization.model_validate(dict(item))
                    for item in available.mappings()
                ],
                mfa_required=bool(mfa_required),
            )


class OrganizationRepository:
    async def create(self, claims: Claims, organization: NewOrganization) -> str:
        # Criar, ativar, trocar e aceitar Convite agem sobre o Usuário, não sobre a Organização
        # ativa: valem mesmo sem o MFA que ela exige (#49), que é como se sai dela.
        async with transaction(claims, {"23505": slug_taken}, check_access=False) as connection:
            result = await connection.execute(
                text(
                    "select doctor.create_organization(:name, :slug, :segment, :llm_provider)::text"
                ),
                organization.model_dump(exclude={"dpa_accepted"}),
            )
            return str(result.scalar_one())

    async def enable(self, claims: Claims, org_id: str, settings: EnabledOrganization) -> str:
        overrides = {"42501": not_owner, "23505": already_enabled}
        async with transaction(claims, overrides, check_access=False) as connection:
            result = await connection.execute(
                text(
                    "select doctor.enable_organization("
                    "cast(:org as uuid), :segment, :llm_provider)::text"
                ),
                {"org": org_id, **settings.model_dump(exclude={"dpa_accepted"})},
            )
            return str(result.scalar_one())

    async def switch(self, claims: Claims, tenant_id: str) -> None:
        async with transaction(claims, {"42501": not_a_member}, check_access=False) as connection:
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
        async with transaction(claims, check_access=False) as connection:
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
