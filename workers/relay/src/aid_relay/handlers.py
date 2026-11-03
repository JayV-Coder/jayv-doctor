"""Rodada do relay, chamada pelo Cloud Scheduler a cada minuto (POST /relay, com OIDC)."""

import os
from functools import lru_cache
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from aid_relay.publisher import PubSubPublisher
from aid_relay.relay import Stats, drain


@lru_cache
def engine() -> AsyncEngine:
    url = os.environ["SUPABASE_DB_URL"].replace("postgresql://", "postgresql+asyncpg://", 1)
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
def publisher() -> PubSubPublisher:
    return PubSubPublisher(
        os.environ["GCP_PROJECT_ID"], emulator_host=os.environ.get("PUBSUB_EMULATOR_HOST")
    )


async def run_relay() -> Stats:
    return await drain(engine(), publisher())
