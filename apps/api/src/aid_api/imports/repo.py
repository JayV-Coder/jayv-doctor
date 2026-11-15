"""Importações dentro de `tenant_tx`. Escritas pelas funções do banco, que conferem o Papel na
tabela e montam o caminho no Storage a partir do tenant da claim."""

import csv
import io
import json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.imports.schemas import Import, ImportMapping, ImportMappingChange, NewImport, Status

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


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Importação ou Integração não encontrada.")


def not_pending() -> ApiError:
    return ApiError(409, "import_not_pending", "Esta Importação já foi concluída ou recusada.")


ERRORS = {
    "P0002": not_found,
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "22023": lambda: ApiError(422, "invalid_filename", "Nome de arquivo inválido."),
    "DR005": not_pending,
    "DR050": lambda: ApiError(429, "quota_exceeded", "A Cota de Eventos do mês foi esgotada."),
}


async def fetch(connection: AsyncConnection, target: str) -> tuple[Import, str | None]:
    result = await connection.execute(
        text(
            f"select {COLUMNS},"  # noqa: S608
            " doctor.import_storage_path(tenant_id, id, format) as storage_path"
            " from doctor.imports where id = cast(:t as uuid)"
        ),
        {"t": target},
    )
    row = result.mappings().first()
    if row is None:
        raise not_found()
    data = dict(row)
    path = data.pop("storage_path")
    return Import.model_validate(data), path


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
                    "select id::text, status, error, duplicate_of::text"
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

    async def get(self, claims: Claims, target: str) -> tuple[Import, str | None]:
        """A Importação e o caminho do objeto no bucket (`None` se recusada antes do upload)."""
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            return await fetch(connection, target)

    async def finish(self, claims: Claims, target: str, size: int, reason: str | None) -> Import:
        """`reason=None` conclui (`uploaded`); com motivo, recusa (`rejected`)."""
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.finish_import(cast(:t as uuid), :size, :reason)"),
                {"t": target, "size": size, "reason": reason},
            )
            return (await fetch(connection, target))[0]

    async def mapping(self, claims: Claims, integration: str) -> ImportMapping:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            exists = await connection.scalar(
                text(
                    "select exists (select 1 from doctor.integrations"
                    " where id = cast(:g as uuid) and archived_at is null)"
                ),
                {"g": integration},
            )
            if not exists:
                raise not_found()
            columns = await connection.scalar(
                text(
                    "select columns from doctor.import_mappings"
                    " where integration_id = cast(:g as uuid)"
                ),
                {"g": integration},
            )
        return ImportMapping(columns=columns or {})

    async def set_mapping(
        self, claims: Claims, integration: str, change: ImportMappingChange
    ) -> ImportMapping:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.set_import_mapping(cast(:g as uuid), cast(:c as jsonb))"),
                {"g": integration, "c": json.dumps(change.columns)},
            )
        return ImportMapping(columns=change.columns)

    async def rejections_csv(self, claims: Claims, target: str) -> tuple[str, str]:
        """O nome do arquivo e o CSV `linha,motivo`, na ordem do arquivo. O motivo é do worker
        (nunca o conteúdo da linha), então não carrega dado do cliente."""
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            current, _ = await fetch(connection, target)
            rows = await connection.execute(
                text(
                    "select line_number, reason from doctor.import_rejections"
                    " where import_id = cast(:i as uuid) order by line_number"
                ),
                {"i": target},
            )
            output = io.StringIO()
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(["linha", "motivo"])
            for line_number, reason in rows:
                writer.writerow([line_number, reason])
        return current.filename, output.getvalue()


def get_import_repository() -> ImportRepository:
    return ImportRepository()
