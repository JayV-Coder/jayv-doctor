"""Acesso a dados com o RLS valendo (ADR-0004): nada de `service_role` em rota de usuário."""

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from aid_api.auth import Claims


@lru_cache
def get_engine() -> AsyncEngine:
    url = os.environ["SUPABASE_DB_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    # O Supavisor em modo transação não preserva prepared statements entre transações.
    return create_async_engine(url, connect_args={"statement_cache_size": 0})


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
