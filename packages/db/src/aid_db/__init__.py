"""Engine do Postgres compartilhado pela API e pelos workers."""

import json
import os
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from aid_observability.tracing import traceparent
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool


def pool_size() -> int:
    """`DB_POOL_SIZE`: conexões guardadas por processo. 0 (o padrão) não guarda nenhuma."""
    try:
        return max(0, int(os.environ.get("DB_POOL_SIZE", "0")))
    except ValueError:
        return 0


def supavisor_engine(url: str) -> AsyncEngine:
    """O Supavisor em modo transação não preserva prepared statements entre transações: nada de
    cache (do asyncpg nem do SQLAlchemy) e nomes únicos.

    Sem `DB_POOL_SIZE`, cada transação abre uma conexão, e o pool é só o do Supavisor (GCP,
    na mesma região do banco). Com ele, o processo guarda até essa quantidade de conexões de
    cliente: no Railway, nos EUA, abrir uma conexão com o banco em São Paulo custa várias idas e
    voltas por requisição. Papel e claims vão sempre por `session_settings` (locais à transação),
    então nada passa de uma transação para outra na mesma conexão."""
    size = pool_size()
    # Sem pré-ping: no asyncpg ele custa três idas e voltas a cada uso, o que se quer evitar.
    # Conexão derrubada é descartada pelo SQLAlchemy no erro, e a reciclagem renova as paradas.
    # Acima de `size`, abre conexões extras como o NullPool (sem fila nem teto por processo).
    pooling: dict[str, Any] = (
        {
            "poolclass": AsyncAdaptedQueuePool,
            "pool_size": size,
            "max_overflow": -1,
            "pool_recycle": 300,
        }
        if size
        else {"poolclass": NullPool}
    )
    return create_async_engine(
        url.replace("postgresql://", "postgresql+asyncpg://", 1),
        **pooling,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
    )


async def propagate_trace(connection: AsyncConnection) -> None:
    """O trace atual vai para a sessão: o trigger da outbox o grava em cada mensagem (#34)."""
    current = traceparent()
    if current:
        await connection.execute(
            text("select set_config('doctor.traceparent', :t, true)"), {"t": current}
        )


ROLES = frozenset({"authenticated", "anon", "service_role"})


async def session_settings(
    connection: AsyncConnection,
    role: str,
    claims: Mapping[str, Any] | None = None,
    request: str = "",
) -> None:
    """Papel, claims do JWT, dados da requisição e trace numa ida e volta só, todos locais à
    transação (`set_config(…, true)`; o de `role` equivale a `set local role`). Com o banco
    longe, cada comando a menos conta, e nada fica na conexão para o próximo uso."""
    if role not in ROLES:
        raise ValueError(f"papel inesperado: {role}")
    settings = ["set_config('role', :role, true)"]
    values: dict[str, str] = {"role": role, "request": request, "trace": traceparent() or ""}
    if claims is not None:
        settings.append("set_config('request.jwt.claims', :claims, true)")
        values["claims"] = json.dumps(claims)
    settings += [
        "set_config('doctor.request', :request, true)",
        # O trace segue pela outbox até os workers (#34).
        "set_config('doctor.traceparent', :trace, true)",
    ]
    await connection.execute(text("select " + ", ".join(settings)), values)


async def platform_role(connection: AsyncConnection) -> None:
    """Jobs de plataforma (workers) agem como service_role, nunca a API (ADR-0004)."""
    await session_settings(connection, "service_role")


async def tenant_role(connection: AsyncConnection, tenant_id: str) -> None:
    """Leitura de um worker em nome de uma Organização: o RLS vale como na API, com a claim do
    tenant e nenhum Usuário. Erro de código que esqueça o filtro não alcança outro tenant."""
    await session_settings(
        connection, "authenticated", {"role": "authenticated", "tenant_id": tenant_id}
    )
