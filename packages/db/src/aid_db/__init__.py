"""Engine do Postgres compartilhado pela API e pelos workers."""

import json
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


def supavisor_engine(url: str) -> AsyncEngine:
    """O Supavisor em modo transação não preserva prepared statements entre transações: nada de
    cache (do asyncpg nem do SQLAlchemy), nomes únicos, e o pool fica por conta do Supavisor."""
    return create_async_engine(
        url.replace("postgresql://", "postgresql+asyncpg://", 1),
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
    )


async def platform_role(connection: AsyncConnection) -> None:
    """Jobs de plataforma (workers) agem como service_role, nunca a API (ADR-0004)."""
    await connection.execute(text("set local role service_role"))


async def tenant_role(connection: AsyncConnection, tenant_id: str) -> None:
    """Leitura de um worker em nome de uma Organização: o RLS vale como na API, com a claim do
    tenant e nenhum Usuário. Erro de código que esqueça o filtro não alcança outro tenant."""
    await connection.execute(text("set local role authenticated"))
    await connection.execute(
        text("select set_config('request.jwt.claims', :claims, true)"),
        {"claims": json.dumps({"role": "authenticated", "tenant_id": tenant_id})},
    )
