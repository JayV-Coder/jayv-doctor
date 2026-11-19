"""Políticas da Organização (#49). Quem muda confere de novo no banco (`set_require_mfa`):
Owner ou Admin com MFA; a auditoria de `tenants` registra a mudança."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.policies.schemas import Policies

ERRORS = {
    "42501": lambda: ApiError(
        403, "forbidden", "Só o Owner ou o Admin, com MFA, mudam as políticas."
    ),
}


class PolicyRepository:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self.engine = engine

    async def get(self, claims: Claims) -> Policies:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            row = (
                (await connection.execute(text("select require_mfa from doctor.tenants")))
                .mappings()
                .one()
            )
            return Policies.model_validate(dict(row))

    async def update(self, claims: Claims, policies: Policies) -> Policies:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.set_require_mfa(:enabled)"),
                {"enabled": policies.require_mfa},
            )
        return await self.get(claims)


def get_policy_repository() -> PolicyRepository:
    return PolicyRepository()
