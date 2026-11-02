"""Acesso a dados com o RLS valendo (ADR-0004): nada de `service_role` em rota de usuário."""

import json
import os
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import lru_cache
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from aid_api.core.auth import Claims
from aid_api.core.errors import ApiError


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


# Transação da requisição, aberta pela idempotência: reserva, efeito e resposta gravada são uma
# coisa só. Quem abre `tenant_tx` com as mesmas claims dentro dela ganha um savepoint.
_request: ContextVar[tuple[Claims, AsyncConnection] | None] = ContextVar("request_tx", default=None)


@asynccontextmanager
async def tenant_tx(
    claims: Claims, engine: AsyncEngine | None = None
) -> AsyncIterator[AsyncConnection]:
    current = _request.get()
    if current is not None and current[0] == claims:
        async with current[1].begin_nested():
            yield current[1]
        return
    async with (engine or get_engine()).begin() as connection:
        await connection.execute(text("set local role authenticated"))
        await connection.execute(
            text("select set_config('request.jwt.claims', :claims, true)"),
            {"claims": json.dumps(claims.raw)},
        )
        yield connection


@asynccontextmanager
async def request_tx(
    claims: Claims, engine: AsyncEngine | None = None
) -> AsyncIterator[AsyncConnection]:
    async with tenant_tx(claims, engine) as connection:
        token = _request.set((claims, connection))
        try:
            yield connection
        finally:
            _request.reset(token)


def sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


@asynccontextmanager
async def translated_tx(
    claims: Claims,
    errors: Mapping[str, Callable[[], ApiError]],
    engine: AsyncEngine | None = None,
) -> AsyncIterator[AsyncConnection]:
    """`tenant_tx` que traduz o SQLSTATE do banco no erro da API de cada módulo."""
    try:
        async with tenant_tx(claims, engine) as connection:
            yield connection
    except DBAPIError as exc:
        factory = errors.get(sqlstate(exc) or "")
        if factory:
            raise factory() from exc
        raise
