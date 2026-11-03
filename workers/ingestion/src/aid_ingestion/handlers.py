"""Tópicos que o worker de ingestão consome. As dependências saem do ambiente do Cloud Run."""

import os
from collections.abc import Awaitable, Callable, Mapping
from functools import lru_cache
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from aid_ingestion.pipeline import process_import
from aid_ingestion.storage import SupabaseObjectStore

Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


@lru_cache
def engine() -> AsyncEngine:
    url = os.environ["SUPABASE_DB_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
    # Supavisor em modo transação: sem cache de prepared statements, como na API.
    return create_async_engine(
        url,
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
    )


@lru_cache
def store() -> SupabaseObjectStore:
    return SupabaseObjectStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def master_key() -> bytes:
    return os.environ["HMAC_MASTER_KEY"].encode()


async def ingestion_raw(payload: Mapping[str, Any]) -> None:
    # Por enquanto só Importações; lotes da API (POST /ingestion/events) entram na parte 3 do #12.
    if "import_id" not in payload:
        raise ValueError("mensagem ingestion.raw sem import_id")
    await process_import(payload, engine(), store(), master_key())


TOPICS: dict[str, Handler] = {"ingestion.raw": ingestion_raw}
