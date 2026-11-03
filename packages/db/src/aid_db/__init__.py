"""Engine do Postgres compartilhado pela API e pelos workers."""

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
