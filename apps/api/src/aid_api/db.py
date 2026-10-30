"""Acesso a dados com o RLS valendo (ADR-0004): nada de `service_role` em rota de usuário."""

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from aid_api.auth import Claims


@lru_cache
def get_engine() -> AsyncEngine:
    url = os.environ["SUPABASE_DB_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    # O Supavisor em modo transação não preserva prepared statements entre transações: nada de
    # cache (do asyncpg nem do SQLAlchemy), nomes únicos e o pool fica por conta do Supavisor.
    return create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
    )


@asynccontextmanager
async def tenant_tx(
    claims: Claims, engine: AsyncEngine | None = None
) -> AsyncIterator[AsyncConnection]:
    async with (engine or get_engine()).begin() as connection:
        await connection.execute(text("set local role authenticated"))
        await connection.execute(
            text("select set_config('request.jwt.claims', :claims, true)"),
            {"claims": json.dumps(claims.raw)},
        )
        yield connection
