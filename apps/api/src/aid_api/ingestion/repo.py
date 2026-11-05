"""Tokens de ingestão e lotes. O sistema externo não tem sessão: as funções do token rodam como
`anon` (`anonymous_tx`), e o tenant sai do próprio token, no banco."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import bindparam

from aid_api.core.auth import Claims
from aid_api.core.db import anonymous_tx, translated_tx
from aid_api.core.errors import ApiError
from aid_api.ingestion.schemas import IngestionToken


@dataclass
class TokenIdentity:
    token_id: str
    tenant_id: str
    integration_id: str


def invalid_token() -> ApiError:
    return ApiError(
        401,
        "invalid_ingestion_token",
        "Token de ingestão ausente, inválido ou revogado.",
        {"WWW-Authenticate": "Bearer"},
    )


ERRORS: dict[str, Callable[[], ApiError]] = {
    "DR006": invalid_token,
    "P0002": lambda: ApiError(404, "not_found", "Integração ou token não encontrado."),
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    # Acima da Cota com a tolerância (110%): o sistema externo deve esperar o próximo mês ou o
    # aumento do plano.
    "DR050": lambda: ApiError(429, "quota_exceeded", "A Cota de Eventos do mês foi esgotada."),
}


class IngestionRepository:
    async def identify(self, token_hash: str) -> TokenIdentity:
        async with anonymous_tx(ERRORS) as connection:
            row = (
                await connection.execute(
                    text(
                        "select token_id::text, tenant_id::text, integration_id::text"
                        " from doctor.resolve_ingestion_token(:h)"
                    ),
                    {"h": token_hash},
                )
            ).one()
            return TokenIdentity(row.token_id, row.tenant_id, row.integration_id)

    async def accept(self, token_hash: str, events: list[dict[str, Any]]) -> str:
        async with anonymous_tx(ERRORS) as connection:
            statement = text("select doctor.accept_ingestion_batch(:h, :events)::text").bindparams(
                bindparam("events", type_=JSONB)
            )
            return str(await connection.scalar(statement, {"h": token_hash, "events": events}))

    async def tokens(self, claims: Claims) -> list[IngestionToken]:
        async with translated_tx(claims, ERRORS) as connection:
            result = await connection.execute(
                text(
                    "select id::text, name, integration_id::text, prefix, created_at,"
                    " last_used_at, revoked_at from doctor.ingestion_tokens"
                    " order by created_at desc"
                )
            )
            return [IngestionToken.model_validate(dict(row)) for row in result.mappings()]

    async def create_token(
        self, claims: Claims, name: str, integration_id: str, token_hash: str, prefix: str
    ) -> str:
        async with translated_tx(claims, ERRORS) as connection:
            result = await connection.scalar(
                text("select doctor.create_ingestion_token(:n, cast(:i as uuid), :h, :p)::text"),
                {"n": name, "i": integration_id, "h": token_hash, "p": prefix},
            )
            return str(result)

    async def revoke_token(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(
                text("select doctor.revoke_ingestion_token(cast(:t as uuid))"), {"t": target}
            )


def get_ingestion_repository() -> IngestionRepository:
    return IngestionRepository()
