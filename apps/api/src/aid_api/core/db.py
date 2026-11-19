"""Acesso a dados com o RLS valendo (ADR-0004): nada de `service_role` em rota de usuário."""

import os
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import lru_cache

from aid_db import session_settings, supavisor_engine
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_api.core import request_meta
from aid_api.core.auth import Claims
from aid_api.core.errors import ApiError


@lru_cache
def get_engine() -> AsyncEngine:
    return supavisor_engine(os.environ["SUPABASE_DB_URL"])


# Transação da requisição, aberta pela idempotência: reserva, efeito e resposta gravada são uma
# coisa só. Quem abre `tenant_tx` com as mesmas claims dentro dela ganha um savepoint.
_request: ContextVar[tuple[Claims, AsyncConnection] | None] = ContextVar("request_tx", default=None)


@asynccontextmanager
async def tenant_tx(
    claims: Claims, engine: AsyncEngine | None = None, *, check_access: bool = True
) -> AsyncIterator[AsyncConnection]:
    current = _request.get()
    if current is not None and current[0] == claims:
        async with current[1].begin_nested():
            yield current[1]
        return
    async with (engine or get_engine()).begin() as connection:
        # IP e request_id vão para a trilha de auditoria (#32).
        await session_settings(
            connection, "authenticated", claims.raw, request_meta.current() or ""
        )
        if check_access and claims.tenant_id is not None:
            # O JWT vale por até 1 h; o Vínculo e as políticas, não: Vínculo removido (SCIM, #48,
            # ou na tela) ou MFA passado a obrigatório (#49), o acesso cai no pedido seguinte.
            problem = await connection.scalar(text("select doctor.access_problem()"))
            if problem == "no_membership":
                raise ApiError(
                    401, "membership_revoked", "Seu acesso a esta Organização foi encerrado."
                )
            if problem == "mfa_required":
                raise ApiError(
                    403,
                    "mfa_required",
                    "Esta Organização exige verificação em duas etapas. Configure-a para entrar.",
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
    *,
    check_access: bool = True,
) -> AsyncIterator[AsyncConnection]:
    """`tenant_tx` que traduz o SQLSTATE do banco no erro da API de cada módulo."""
    try:
        async with tenant_tx(claims, engine, check_access=check_access) as connection:
            yield connection
    except DBAPIError as exc:
        factory = errors.get(sqlstate(exc) or "")
        if factory:
            raise factory() from exc
        raise


@asynccontextmanager
async def anonymous_tx(
    errors: Mapping[str, Callable[[], ApiError]], engine: AsyncEngine | None = None
) -> AsyncIterator[AsyncConnection]:
    """Transação sem Usuário (sistema externo com token de ingestão): role `anon`, sem claims.
    Só alcança as funções do banco liberadas para `anon`, que identificam o tenant pelo token."""
    try:
        async with (engine or get_engine()).begin() as connection:
            # IP, request_id e o trace também sem Usuário (#32, #34).
            await session_settings(connection, "anon", request=request_meta.current() or "")
            yield connection
    except DBAPIError as exc:
        factory = errors.get(sqlstate(exc) or "")
        if factory:
            raise factory() from exc
        raise
