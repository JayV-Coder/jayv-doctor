"""Tópicos que o worker de ingestão consome. As dependências saem do ambiente do Cloud Run."""

import os
from collections.abc import Awaitable, Callable, Mapping
from functools import lru_cache
from typing import Any

from aid_db import supavisor_engine
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_ingestion.pipeline import process_import
from aid_ingestion.storage import SupabaseObjectStore

Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


@lru_cache
def engine() -> AsyncEngine:
    return supavisor_engine(os.environ["SUPABASE_DB_URL"])


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
