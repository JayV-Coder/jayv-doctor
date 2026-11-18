"""Engine do Postgres compartilhado pela API e pelos workers."""

import json
import os
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
    cliente (mais o mesmo tanto de folga) e confere cada uma antes de usar: no Railway, nos EUA,
    abrir uma conexão com o banco em São Paulo custa várias idas e voltas por requisição. As
    variáveis de sessão são sempre `set local`, então nada passa de uma transação para outra."""
    size = pool_size()
    pooling: dict[str, Any] = (
        {
            "poolclass": AsyncAdaptedQueuePool,
            "pool_size": size,
            "max_overflow": size,
            "pool_pre_ping": True,
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


async def platform_role(connection: AsyncConnection) -> None:
    """Jobs de plataforma (workers) agem como service_role, nunca a API (ADR-0004)."""
    await connection.execute(text("set local role service_role"))
    await propagate_trace(connection)


async def tenant_role(connection: AsyncConnection, tenant_id: str) -> None:
    """Leitura de um worker em nome de uma Organização: o RLS vale como na API, com a claim do
    tenant e nenhum Usuário. Erro de código que esqueça o filtro não alcança outro tenant."""
    await connection.execute(text("set local role authenticated"))
    await connection.execute(
        text("select set_config('request.jwt.claims', :claims, true)"),
        {"claims": json.dumps({"role": "authenticated", "tenant_id": tenant_id})},
    )
    await propagate_trace(connection)
