"""SSO dentro de `tenant_tx`: configurar é do Owner com MFA (o banco confere em
`doctor.require_sso_owner`); descobrir o SSO de um e-mail é anônimo; provisionar é de quem
acabou de entrar pelo IdP, ainda sem Organização no token."""

import json
import os
import secrets

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_api.core.auth import Claims
from aid_api.core.db import anonymous_tx, translated_tx
from aid_api.core.errors import ApiError
from aid_api.core.tokens import token_hash
from aid_api.sso.schemas import (
    ScimToken,
    SsoConfigIn,
    SsoConnection,
    SsoDiscovery,
    SsoDomain,
    SsoGroupsIn,
    SsoProvisioned,
    SsoSettings,
)


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Domínio não encontrado.")


ERRORS = {
    "42501": lambda: ApiError(403, "forbidden", "Só o Owner, com MFA, configura o SSO."),
    "P0002": not_found,
    "23514": lambda: ApiError(422, "invalid", "Dados recusados pelo banco."),
    "22023": lambda: ApiError(422, "invalid", "Mapeamento de grupos inválido."),
    "DR100": lambda: ApiError(409, "domain_taken", "Este domínio já está cadastrado."),
    "DR101": lambda: ApiError(
        422, "domain_required", "Exigir SSO pede ao menos um domínio verificado."
    ),
    "DR102": lambda: ApiError(409, "sso_not_configured", "Configure o SSO antes."),
}
PROVISION_ERRORS = {
    "DR103": lambda: ApiError(
        403, "sso_inactive", "O SSO desta Organização não está ativo. Fale com o Owner."
    ),
    "DR104": lambda: ApiError(403, "sso_deactivated", "Seu usuário está desativado no IdP."),
    "DR051": lambda: ApiError(
        409, "plan_limit", "O plano da Organização chegou ao limite de membros. Fale com o Owner."
    ),
}


def txt_name(domain: str) -> str:
    return f"_aid-sso.{domain}"


def scim_base_url() -> str:
    return os.environ.get("AID_PUBLIC_API_URL", "").rstrip("/") + "/scim/v2"


class SsoRepository:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self.engine = engine

    async def settings(self, claims: Claims) -> SsoSettings:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            # O hash do token SCIM não é legível pelo `authenticated`: só se há um.
            row = (
                (
                    await connection.execute(
                        text(
                            "select id::text, status, metadata_url, require_sso, default_role,"
                            " last_error, updated_at,"
                            " doctor.sso_scim_enabled() as scim_enabled"
                            " from doctor.sso_connections"
                        )
                    )
                )
                .mappings()
                .first()
            )
            domains = (
                await connection.execute(
                    text(
                        "select id::text, domain, token, verified_at from doctor.sso_domains"
                        " order by domain"
                    )
                )
            ).mappings()
            groups = (
                await connection.execute(
                    text("select group_name, role from doctor.sso_group_roles order by group_name")
                )
            ).mappings()
            return SsoSettings(
                connection=SsoConnection.model_validate(dict(row)) if row else None,
                domains=[
                    SsoDomain(
                        id=item["id"],
                        domain=item["domain"],
                        verified_at=item["verified_at"],
                        txt_name=txt_name(item["domain"]),
                        txt_value=f"aid-sso={item['token']}",
                    )
                    for item in domains
                ],
                groups={item["group_name"]: item["role"] for item in groups},
            )

    async def configure(self, claims: Claims, config: SsoConfigIn) -> SsoSettings:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.configure_sso(:m, :r, :d)"),
                {"m": config.metadata_url, "r": config.require_sso, "d": config.default_role},
            )
        return await self.settings(claims)

    async def disable(self, claims: Claims) -> None:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(text("select doctor.disable_sso()"))

    async def add_domain(self, claims: Claims, domain: str) -> SsoDomain:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            created = await connection.scalar(
                text("select doctor.add_sso_domain(:d)"), {"d": domain}
            )
            row = (
                (
                    await connection.execute(
                        text(
                            "select id::text, domain, token, verified_at from doctor.sso_domains"
                            " where id = :i"
                        ),
                        {"i": created},
                    )
                )
                .mappings()
                .one()
            )
        return SsoDomain(
            id=row["id"],
            domain=row["domain"],
            verified_at=row["verified_at"],
            txt_name=txt_name(row["domain"]),
            txt_value=f"aid-sso={row['token']}",
        )

    async def verify_domain(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.verify_sso_domain(cast(:t as uuid))"), {"t": target}
            )

    async def remove_domain(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.remove_sso_domain(cast(:t as uuid))"), {"t": target}
            )

    async def set_groups(self, claims: Claims, groups: SsoGroupsIn) -> SsoSettings:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.set_sso_groups(cast(:g as jsonb))"),
                {"g": json.dumps(groups.groups)},
            )
        return await self.settings(claims)

    async def rotate_scim_token(self, claims: Claims) -> ScimToken:
        token = secrets.token_urlsafe(32)
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.set_scim_token(:h)"), {"h": token_hash(token)}
            )
        return ScimToken(token=token, base_url=scim_base_url())

    async def discover(self, email: str) -> SsoDiscovery:
        async with anonymous_tx({}, self.engine) as connection:
            row = (
                (
                    await connection.execute(
                        text("select domain, required from doctor.sso_discover(:e)"), {"e": email}
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return SsoDiscovery(sso=False, required=False, domain=None)
        return SsoDiscovery(sso=True, required=row["required"], domain=row["domain"])

    async def provision(self, claims: Claims) -> SsoProvisioned:
        async with translated_tx(claims, PROVISION_ERRORS, self.engine) as connection:
            row = (
                (
                    await connection.execute(
                        text("select tenant_id::text, role from doctor.sso_provision()")
                    )
                )
                .mappings()
                .first()
            )
        # Fora da transação: sem grupo mapeado, o banco já tirou o Vínculo, e isso fica gravado.
        if row is None:
            raise ApiError(
                403,
                "sso_no_group",
                "Seu grupo no IdP não dá acesso a esta Organização. Fale com o Owner.",
            )
        return SsoProvisioned(tenant_id=row["tenant_id"], role=row["role"])


def get_sso_repository() -> SsoRepository:
    return SsoRepository()
