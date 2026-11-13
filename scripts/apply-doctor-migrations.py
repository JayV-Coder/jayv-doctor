"""Aplica as migrações do Doctor no projeto compartilhado com o jayv-coder (ADR-0009).

`--check` só lê: confere o que o Doctor usa em `public` e lista o que falta aplicar.
`--apply` aplica cada arquivo pendente numa transação e registra em `doctor.schema_migrations`.

As migrações vêm do submódulo `vendor/supabase` (ADR-0022). As dos outros schemas, na mesma
pasta, são aplicadas pelo deploy daquele repositório (`supabase db push` a cada merge na `main`),
nunca por aqui.

    SUPABASE_DB_URL=... uv run python scripts/apply-doctor-migrations.py --check
"""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import asyncpg

MIGRATIONS = Path(__file__).parent.parent / "vendor" / "supabase" / "migrations"
# Do Doctor é só o arquivo com `_doctor_` logo depois da versão: `<versão>_site_doctor_x.sql` é
# de outro app e vai pelo `db push`.
DOCTOR_NAME = re.compile(r"^\d+_doctor_.+\.sql$")


class MigrationsMissingError(RuntimeError):
    pass


def doctor_migrations(folder: Path) -> list[Path]:
    found = (
        sorted(path for path in folder.glob("*.sql") if DOCTOR_NAME.match(path.name))
        if folder.is_dir()
        else []
    )
    if not found:
        # Sem o submódulo, a pasta fica vazia: "nada pendente" seria mentira.
        raise MigrationsMissingError(
            f"nenhuma migração do Doctor em {folder}: rode `git submodule update --init`"
        )
    return found


def version_of(migration: Path) -> str:
    return migration.name.split("_", 1)[0]


def shared_not_deployed(folder: Path, pending: list[Path], deployed: set[str]) -> list[str]:
    """Migrações dos outros schemas anteriores à última pendente do Doctor que o deploy ainda não
    aplicou. Localmente tudo sobe em ordem; aqui, uma do Doctor que dependa delas falharia."""
    if not pending:
        return []
    newest = max(version_of(migration) for migration in pending)
    return [
        path.name
        for path in sorted(folder.glob("*.sql"))
        if not DOCTOR_NAME.match(path.name)
        and version_of(path) < newest
        and version_of(path) not in deployed
    ]


# O que o Doctor lê em `public`: renomear algo aqui no jayv-coder quebra o Doctor.
REQUIRED_COLUMNS = {
    "organizations": {"id", "name", "slug"},
    "organization_members": {"org_id", "user_id", "role"},
    "profiles": {"user_id", "display_name", "avatar_url"},
}
REQUIRED_FUNCTIONS = ["public.create_organization(text, text)"]


async def public_problems(connection: asyncpg.Connection) -> list[str]:
    problems = []
    for table, required in REQUIRED_COLUMNS.items():
        rows = await connection.fetch(
            "select column_name from information_schema.columns"
            " where table_schema = 'public' and table_name = $1",
            table,
        )
        missing = required - {row["column_name"] for row in rows}
        if missing:
            problems.append(f"public.{table}: faltam {sorted(missing)}")
    for function in REQUIRED_FUNCTIONS:
        if await connection.fetchval("select to_regprocedure($1)", function) is None:
            problems.append(f"{function}: não existe")
    return problems


async def applied_versions(connection: asyncpg.Connection) -> set[str]:
    if await connection.fetchval("select to_regclass('doctor.schema_migrations')") is None:
        return set()
    rows = await connection.fetch("select version from doctor.schema_migrations")
    return {row["version"] for row in rows}


async def deployed_versions(connection: asyncpg.Connection) -> set[str]:
    """O histórico do `supabase db push` (o deploy de JayV-Coder/supabase)."""
    if (
        await connection.fetchval("select to_regclass('supabase_migrations.schema_migrations')")
        is None
    ):
        return set()
    rows = await connection.fetch("select version from supabase_migrations.schema_migrations")
    return {row["version"] for row in rows}


async def run(apply: bool) -> int:
    try:
        migrations = doctor_migrations(MIGRATIONS)
    except MigrationsMissingError as exc:
        print(exc, file=sys.stderr)
        return 1
    connection = await asyncpg.connect(os.environ["SUPABASE_DB_URL"], statement_cache_size=0)
    try:
        problems = await public_problems(connection)
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 1

        applied = await applied_versions(connection)
        pending = [migration for migration in migrations if version_of(migration) not in applied]
        behind = shared_not_deployed(MIGRATIONS, pending, await deployed_versions(connection))
        if behind:
            print(
                "aviso: o deploy de JayV-Coder/supabase ainda não aplicou migrações anteriores"
                " às pendentes do Doctor: " + ", ".join(behind),
                file=sys.stderr,
            )
        for migration in pending:
            print(("aplicando " if apply else "pendente ") + migration.name)
            if not apply:
                continue
            async with connection.transaction():
                await connection.execute(migration.read_text(encoding="utf-8"))
                await connection.execute(
                    "insert into doctor.schema_migrations (version) values ($1)",
                    version_of(migration),
                )
        return 0
    finally:
        await connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return asyncio.run(run(parser.parse_args().apply))


if __name__ == "__main__":
    sys.exit(main())
