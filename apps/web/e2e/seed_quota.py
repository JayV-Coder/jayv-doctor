"""Esgota a Cota de IA do mês da Organização do E2E (ticket #31). Roda com `uv run python` na
raiz do repositório.

Uso: seed_quota.py <nome da Organização>
"""

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

DB = os.environ.get("E2E_DB_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres")


async def main(organization: str) -> None:
    engine = create_async_engine(DB, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into doctor.usage_records (tenant_id, resource, period_start, quantity)"
                " select o.id, 'diagnoses_llm', doctor.usage_period('diagnoses_llm'), 1000"
                " from public.organizations o where o.name = :n"
                " on conflict (tenant_id, resource, period_start) do update set quantity = 1000"
            ),
            {"n": organization},
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
