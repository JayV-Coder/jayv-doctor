"""Gera, como o worker de diagnóstico, os Relatórios técnicos na fila da Organização do E2E
(ticket #32), no Storage local. Roda com `uv run python` na raiz do repositório.

Uso: seed_report.py <nome da Organização>
"""

import asyncio
import os
import sys

from aid_diagnosis_worker.report import generate_report
from aid_diagnosis_worker.retention import SupabaseStorage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

DB = os.environ.get("E2E_DB_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres")
STORAGE = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321")


async def main(organization: str) -> None:
    engine = create_async_engine(DB, poolclass=NullPool)
    storage = SupabaseStorage(STORAGE, os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    async with engine.begin() as connection:
        reports = (
            await connection.execute(
                text(
                    "select r.id::text from doctor.reports r"
                    " join public.organizations o on o.id = r.tenant_id"
                    " where o.name = :n and r.status = 'queued'"
                ),
                {"n": organization},
            )
        ).scalars()
        queued = list(reports)
    for report in queued:
        await generate_report(engine, {"report_id": report}, storage)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
