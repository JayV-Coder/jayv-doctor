"""Agentes da Organização ativa, dentro de `tenant_tx`: o RLS e as funções do banco valem."""

import secrets

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import bindparam

from aid_api.agents.schemas import Agent
from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.core.tokens import token_hash

ERRORS = {
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "P0002": lambda: ApiError(404, "not_found", "Agente ou Integração não encontrado."),
}
COLUMNS = (
    "id::text, integration_id::text, name, status, config, config_version, cert_fingerprint,"
    " version, last_seen_at, registered_at, revoked_at, registration_expires_at, created_at"
)
TOKEN_PREFIX = "aid_reg_"  # noqa: S105 - prefixo, não segredo


def new_token() -> tuple[str, str]:
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, token_hash(token)


class AgentRepository:
    async def list(self, claims: Claims) -> list[Agent]:
        async with translated_tx(claims, ERRORS) as connection:
            result = await connection.execute(
                text(f"select {COLUMNS} from doctor.agents order by created_at desc")  # noqa: S608
            )
            return [Agent.model_validate(dict(row)) for row in result.mappings()]

    async def create(
        self, claims: Claims, name: str, integration: str, config: dict[str, object]
    ) -> tuple[str, str]:
        token, hashed = new_token()
        async with translated_tx(claims, ERRORS) as connection:
            statement = text(
                "select doctor.create_agent(:n, cast(:i as uuid), :h, :c)::text"
            ).bindparams(bindparam("c", type_=JSONB))
            created = await connection.scalar(
                statement, {"n": name, "i": integration, "h": hashed, "c": config}
            )
        return str(created), token

    async def change_config(self, claims: Claims, target: str, config: dict[str, object]) -> int:
        async with translated_tx(claims, ERRORS) as connection:
            statement = text("select doctor.update_agent_config(cast(:a as uuid), :c)").bindparams(
                bindparam("c", type_=JSONB)
            )
            return int(await connection.scalar(statement, {"a": target, "c": config}) or 0)

    async def revoke(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(
                text("select doctor.revoke_agent(cast(:a as uuid))"), {"a": target}
            )

    async def rotate(self, claims: Claims, target: str) -> str:
        token, hashed = new_token()
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(
                text("select doctor.rotate_agent(cast(:a as uuid), :h)"), {"a": target, "h": hashed}
            )
        return token


def get_agents_repository() -> AgentRepository:
    return AgentRepository()
