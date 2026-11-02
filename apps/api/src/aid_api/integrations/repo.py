"""Acesso a Integrações dentro de `tenant_tx`: o RLS limita à Organização ativa e só deixa
Owner e Admin com MFA escreverem, com o Papel lido da tabela (`doctor.is_manager`)."""

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.integrations.schemas import Integration, IntegrationChange, NewIntegration

# As colunas são constantes daqui; o `noqa: S608` nas consultas se apoia nisso.
COLUMNS = (
    "id::text, name, description, source_system, target_system, owner_team, environment,"
    " archived_at, created_at"
)
# Lista fechada: os nomes de coluna entram no SQL, os valores vão sempre como parâmetro.
UPDATABLE = ("name", "description", "source_system", "target_system", "owner_team", "environment")


def integration_exists() -> ApiError:
    return ApiError(
        409, "integration_exists", "Já existe uma Integração com este nome neste Ambiente."
    )


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Integração não encontrada.")


def forbidden() -> ApiError:
    return ApiError(403, "forbidden", "Seu Papel não permite esta ação.")


def integration_archived() -> ApiError:
    return ApiError(409, "integration_archived", "Integração arquivada não muda.")


ERRORS = {"23505": integration_exists, "42501": forbidden}


async def visible(connection: AsyncConnection, target: str) -> Integration:
    """A linha como o RLS de leitura a mostra; `not_found` se não existe nesta Organização."""
    result = await connection.execute(
        text(f"select {COLUMNS} from doctor.integrations where id = cast(:target as uuid)"),  # noqa: S608
        {"target": target},
    )
    row = result.mappings().first()
    if row is None:
        raise not_found()
    return Integration.model_validate(dict(row))


# Um update que não alcançou a linha pode ser falta de Papel (o RLS de escrita lê o Papel da
# tabela, e a claim pode estar atrasada), Integração arquivada ou de outra Organização.
async def missed(connection: AsyncConnection, target: str) -> Integration:
    current = await visible(connection, target)
    if current.archived_at is not None:
        return current
    raise forbidden()


def to_integration(row: RowMapping) -> Integration:
    return Integration.model_validate(dict(row))


class IntegrationRepository:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self.engine = engine

    async def list(self, claims: Claims, *, include_archived: bool) -> list[Integration]:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            result = await connection.execute(
                text(
                    f"select {COLUMNS} from doctor.integrations"  # noqa: S608
                    " where (:include_archived or archived_at is null)"
                    " order by name, environment"
                ),
                {"include_archived": include_archived},
            )
            return [Integration.model_validate(dict(row)) for row in result.mappings()]

    async def create(self, claims: Claims, new: NewIntegration) -> Integration:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            result = await connection.execute(
                text(
                    "insert into doctor.integrations"  # noqa: S608
                    " (name, description, source_system, target_system, owner_team, environment)"
                    " values (:name, :description, :source_system, :target_system, :owner_team,"
                    f" :environment) returning {COLUMNS}"
                ),
                new.model_dump(),
            )
            row = result.mappings().first()
            if row is None:
                raise forbidden()
            return to_integration(row)

    async def update(self, claims: Claims, target: str, change: IntegrationChange) -> Integration:
        values = {
            key: value
            for key, value in change.model_dump(exclude_unset=True).items()
            if key in UPDATABLE
        }
        assignments = ", ".join(f"{column} = :{column}" for column in values)
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            result = await connection.execute(
                text(
                    f"update doctor.integrations set {assignments}"  # noqa: S608
                    f" where id = cast(:target as uuid) returning {COLUMNS}"
                ),
                {**values, "target": target},
            )
            row = result.mappings().first()
            if row is None:
                await missed(connection, target)
                raise integration_archived()
            return to_integration(row)

    # Arquivar de novo devolve a arquivada, com a data original: a operação é idempotente.
    async def archive(self, claims: Claims, target: str) -> Integration:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            result = await connection.execute(
                text(
                    "update doctor.integrations set archived_at = now()"  # noqa: S608
                    f" where id = cast(:target as uuid) returning {COLUMNS}"
                ),
                {"target": target},
            )
            row = result.mappings().first()
            return to_integration(row) if row else await missed(connection, target)


def get_integration_repository() -> IntegrationRepository:
    return IntegrationRepository()
