"""Importações dentro de `tenant_tx`. Escritas pelas funções do banco, que conferem o Papel na
tabela e montam o caminho no Storage a partir do tenant da claim."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.imports.schemas import Import, NewImport, Status

COLUMNS = (
    "id::text, integration_id::text, filename, size_bytes, format, status, duplicate_of::text,"
    " total_lines, accepted, rejected, duplicates, secrets_removed, error, created_at"
)


@dataclass
class CreatedRow:
    id: str
    status: Status
    error: str | None
    duplicate_of: str | None
    storage_path: str | None


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Importação ou Integração não encontrada.")


def not_pending() -> ApiError:
    return ApiError(409, "import_not_pending", "Esta Importação já foi concluída ou recusada.")


ERRORS = {
    "P0002": not_found,
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "22023": lambda: ApiError(422, "invalid_filename", "Nome de arquivo inválido."),
    "DR005": not_pending,
}


async def fetch(connection: AsyncConnection, target: str) -> Import:
    result = await connection.execute(
        text(f"select {COLUMNS} from doctor.imports where id = cast(:t as uuid)"),  # noqa: S608
        {"t": target},
    )
    row = result.mappings().first()
    if row is None:
        raise not_found()
    return Import.model_validate(dict(row))


class ImportRepository:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self.engine = engine

    async def list(self, claims: Claims) -> list[Import]:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            result = await connection.execute(
                text(
                    f"select {COLUMNS} from doctor.imports"  # noqa: S608
                    " order by created_at desc limit 50"
                )
            )
            return [Import.model_validate(dict(row)) for row in result.mappings()]

    async def create(self, claims: Claims, new: NewImport) -> CreatedRow:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            result = await connection.execute(
                text(
                    "select id::text, status, error, duplicate_of::text, storage_path"
                    " from doctor.create_import(cast(:integration as uuid), :filename, :size, :sha)"
                ),
                {
                    "integration": str(new.integration_id),
                    "filename": new.filename,
                    "size": new.size_bytes,
                    "sha": new.sha256,
                },
            )
            return CreatedRow(**result.mappings().one())

    async def get(self, claims: Claims, target: str) -> tuple[Import, str]:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            current = await fetch(connection, target)
            path = await connection.scalar(
                text(
                    "select tenant_id || '/imports/' || id || '/' || filename"
                    " from doctor.imports where id = cast(:t as uuid)"
                ),
                {"t": target},
            )
            return current, str(path)

    async def complete(self, claims: Claims, target: str, size: int) -> Import:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.complete_import(cast(:t as uuid), :size)"),
                {"t": target, "size": size},
            )
            return await fetch(connection, target)

    async def reject(self, claims: Claims, target: str, reason: str, size: int) -> Import:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.reject_import(cast(:t as uuid), :reason, :size)"),
                {"t": target, "reason": reason, "size": size},
            )
            return await fetch(connection, target)


def get_import_repository() -> ImportRepository:
    return ImportRepository()
