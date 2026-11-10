"""Mapas de identificadores dentro de `tenant_tx`: o RLS limita à Organização ativa e só deixa
Owner e Admin com MFA escreverem."""

import json
from typing import Any

from aid_correlation import MappingError, dump_keys, parse_keys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.correlation.schemas import CorrelationMapping, Lookup, MappingChange, MappingIn

COLUMNS = (
    "id::text, integration_id::text, name, keys, window_minutes, reconcile, lookup,"
    " created_at, updated_at"
)
# Provedores com consulta de enriquecimento (aid_connectors.*.lookup).
LOOKUP_PROVIDERS = ("salesforce", "odata")


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Integração ou Mapa não encontrado.")


def forbidden() -> ApiError:
    return ApiError(403, "forbidden", "Seu Papel não permite esta ação.")


ERRORS = {
    "23505": lambda: ApiError(409, "mapping_exists", "Já existe um Mapa com este nome."),
    "23503": not_found,
    "42501": forbidden,
}


def invalid(detail: str) -> ApiError:
    return ApiError(422, "invalid_mapping", f"Mapa inválido ({detail}).")


def clean_keys(raw: list[dict[str, Any]]) -> str:
    try:
        return json.dumps(dump_keys(parse_keys(raw)))
    except MappingError as exc:
        raise invalid(str(exc)) from exc


async def clean_lookup(connection: AsyncConnection, lookup: Lookup | None) -> str | None:
    if lookup is None:
        return None
    provider = await connection.scalar(
        text("select provider from doctor.connectors where id = cast(:c as uuid)"),
        {"c": str(lookup.connector_id)},
    )
    if provider is None:
        raise invalid("lookup.connector_id: Conector desta Organização")
    if provider not in LOOKUP_PROVIDERS:
        raise invalid(f"lookup.connector_id: Conector {' ou '.join(LOOKUP_PROVIDERS)}")
    return lookup.model_dump_json()


def to_mapping(row: Any) -> CorrelationMapping:
    return CorrelationMapping.model_validate(dict(row))


class MappingRepository:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self.engine = engine

    async def list(self, claims: Claims, integration: str) -> list[CorrelationMapping]:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            exists = await connection.scalar(
                text("select 1 from doctor.integrations where id = cast(:i as uuid)"),
                {"i": integration},
            )
            if exists is None:
                raise not_found()
            result = await connection.execute(
                text(
                    f"select {COLUMNS} from doctor.correlation_mappings"  # noqa: S608
                    " where integration_id = cast(:i as uuid) order by name"
                ),
                {"i": integration},
            )
            return [to_mapping(row) for row in result.mappings()]

    async def create(self, claims: Claims, integration: str, new: MappingIn) -> CorrelationMapping:
        keys = clean_keys(new.keys)
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            lookup = await clean_lookup(connection, new.lookup)
            row = (
                (
                    await connection.execute(
                        text(
                            "insert into doctor.correlation_mappings (integration_id, name, keys,"  # noqa: S608
                            " window_minutes, reconcile, lookup) values (cast(:i as uuid), :n,"
                            " cast(:k as jsonb), :w, :r, cast(:l as jsonb))"
                            f" returning {COLUMNS}"
                        ),
                        {
                            "i": integration,
                            "n": new.name.strip(),
                            "k": keys,
                            "w": new.window_minutes,
                            "r": new.reconcile,
                            "l": lookup,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise forbidden()
            return to_mapping(row)

    async def update(
        self, claims: Claims, target: str, change: MappingChange
    ) -> CorrelationMapping:
        values: dict[str, Any] = {}
        if change.name is not None:
            values["name"] = change.name.strip()
        if change.keys is not None:
            values["keys"] = clean_keys(change.keys)
        if change.window_minutes is not None:
            values["window_minutes"] = change.window_minutes
        if change.reconcile is not None:
            values["reconcile"] = change.reconcile
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            if change.lookup is not None:
                values["lookup"] = await clean_lookup(connection, change.lookup)
            elif change.clear_lookup:
                values["lookup"] = None
            if not values:
                return await self.one(connection, target)
            casts = {"keys": "cast(:keys as jsonb)", "lookup": "cast(:lookup as jsonb)"}
            assignments = ", ".join(f"{name} = {casts.get(name, ':' + name)}" for name in values)
            row = (
                (
                    await connection.execute(
                        text(
                            f"update doctor.correlation_mappings set {assignments}"  # noqa: S608
                            f" where id = cast(:target as uuid) returning {COLUMNS}"
                        ),
                        {**values, "target": target},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                await self.one(connection, target)
                raise forbidden()
            return to_mapping(row)

    async def one(self, connection: AsyncConnection, target: str) -> CorrelationMapping:
        row = (
            (
                await connection.execute(
                    text(
                        f"select {COLUMNS} from doctor.correlation_mappings"  # noqa: S608
                        " where id = cast(:m as uuid)"
                    ),
                    {"m": target},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise not_found()
        return to_mapping(row)

    async def delete(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            deleted = await connection.scalar(
                text(
                    "delete from doctor.correlation_mappings"
                    " where id = cast(:m as uuid) returning id"
                ),
                {"m": target},
            )
            if deleted is None:
                await self.one(connection, target)
                raise forbidden()


def get_mapping_repository() -> MappingRepository:
    return MappingRepository()
