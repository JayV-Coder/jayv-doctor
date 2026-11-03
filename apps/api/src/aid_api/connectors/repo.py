"""Conectores dentro de `tenant_tx`: leitura pelo RLS; escrita pelas funções do banco, que
conferem Owner/Admin com MFA na tabela e guardam a credencial no Vault."""

import json
from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from aid_api.connectors.schemas import Connector, ConnectorChange, ConnectorSync, NewConnector
from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError

COLUMNS = (
    "c.id::text, c.integration_id::text, c.provider, c.name, c.config, c.status, c.paused_reason,"
    " c.consecutive_failures, c.sync_interval_seconds, c.checkpoint, c.last_sync_at,"
    " c.last_error, c.next_run_at, c.created_at,"
    " (select s.records from doctor.connector_syncs s"
    "  where s.tenant_id = c.tenant_id and s.connector_id = c.id and s.finished_at is not null"
    "  order by s.started_at desc limit 1) as last_sync_records"
)
ACTIONS = {
    "sync": "doctor.request_connector_sync",
    "pause": "doctor.pause_connector",
    "resume": "doctor.resume_connector",
}


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Conector ou Integração não encontrado.")


ERRORS = {
    "P0002": not_found,
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "23514": lambda: ApiError(422, "validation_error", "Os dados enviados são inválidos."),
    "DR007": lambda: ApiError(409, "connector_paused", "Retome o Conector antes de sincronizar."),
    "DR008": lambda: ApiError(409, "connector_disabled", "Conector desativado pela plataforma."),
    "DR009": lambda: ApiError(409, "sync_running", "Já há uma Sincronização em andamento."),
}


async def fetch(connection: AsyncConnection, target: str) -> Connector:
    row: RowMapping | None = (
        (
            await connection.execute(
                text(f"select {COLUMNS} from doctor.connectors c where c.id = cast(:c as uuid)"),  # noqa: S608
                {"c": target},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise not_found()
    return Connector.model_validate(dict(row))


class ConnectorRepository:
    async def all(self, claims: Claims) -> list[Connector]:
        async with translated_tx(claims, ERRORS) as connection:
            result = await connection.execute(
                text(f"select {COLUMNS} from doctor.connectors c order by c.created_at desc")  # noqa: S608
            )
            return [Connector.model_validate(dict(row)) for row in result.mappings()]

    async def get(self, claims: Claims, target: str) -> Connector:
        async with translated_tx(claims, ERRORS) as connection:
            return await fetch(connection, target)

    async def create(self, claims: Claims, new: NewConnector) -> Connector:
        async with translated_tx(claims, ERRORS) as connection:
            created = await connection.scalar(
                text(
                    "select doctor.create_connector(cast(:i as uuid), :p, :n,"
                    " cast(:c as jsonb), :s, :v)::text"
                ),
                {
                    "i": str(new.integration_id),
                    "p": new.provider,
                    "n": new.name,
                    "c": json.dumps(new.config),
                    "s": new.credential.get_secret_value(),
                    "v": new.sync_interval_seconds or 300,
                },
            )
            return await fetch(connection, str(created))

    async def update(
        self,
        claims: Claims,
        target: str,
        change: ConnectorChange,
        check_config: Callable[[str, Mapping[str, Any]], None],
    ) -> Connector:
        async with translated_tx(claims, ERRORS) as connection:
            if change.config is not None:
                # Na mesma transação da alteração: o provedor lido é o que vai valer.
                check_config((await fetch(connection, target)).provider, change.config)
            if change.name is not None or change.config is not None or change.sync_interval_seconds:
                await connection.execute(
                    text(
                        "select doctor.update_connector(cast(:t as uuid), :n,"
                        " cast(:c as jsonb), :i)"
                    ),
                    {
                        "t": target,
                        "n": change.name,
                        "c": json.dumps(change.config) if change.config is not None else None,
                        "i": change.sync_interval_seconds,
                    },
                )
            if change.credential is not None:
                await connection.execute(
                    text("select doctor.put_connector_secret(cast(:t as uuid), :s)"),
                    {"t": target, "s": change.credential.get_secret_value()},
                )
            return await fetch(connection, target)

    async def action(self, claims: Claims, target: str, name: str) -> None:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(
                text(f"select {ACTIONS[name]}(cast(:t as uuid))"),
                {"t": target},
            )

    async def syncs(self, claims: Claims, target: str) -> list[ConnectorSync]:
        async with translated_tx(claims, ERRORS) as connection:
            await fetch(connection, target)
            result = await connection.execute(
                text(
                    "select id::text, started_at, finished_at, status, records, error"
                    " from doctor.connector_syncs where connector_id = cast(:c as uuid)"
                    " order by started_at desc limit 50"
                ),
                {"c": target},
            )
            return [ConnectorSync.model_validate(dict(row)) for row in result.mappings()]


def get_connector_repository() -> ConnectorRepository:
    return ConnectorRepository()
