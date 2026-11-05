"""Tópico `correlation.requested` e rota do fechamento do worker de correlação."""

import os
from collections.abc import Awaitable, Callable, Mapping
from functools import lru_cache
from typing import Any

from aid_db import supavisor_engine
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_correlation_worker.audit import import_auth_events
from aid_correlation_worker.close import close_idle
from aid_correlation_worker.correlate import correlate_integration
from aid_correlation_worker.stats import refresh_stats, rollup_usage

Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


@lru_cache
def engine() -> AsyncEngine:
    return supavisor_engine(os.environ["SUPABASE_DB_URL"])


async def correlation_requested(payload: Mapping[str, Any]) -> None:
    # A ingestão manda {import_id | batch_id, integration_id}; a continuação, só a Integração.
    await correlate_integration(engine(), payload)


TOPICS: dict[str, Handler] = {"correlation.requested": correlation_requested}

router = APIRouter()


@router.post("/close")
async def close() -> dict[str, int]:
    return {"closed": await close_idle(engine())}


@router.post("/stats")
async def stats() -> dict[str, int]:
    """Job de 10 min: o agregado do Dashboard (#21) e a soma dos deltas de uso (#31)."""
    hours = await refresh_stats(engine())
    return {"hours": hours, "usage": await rollup_usage(engine())}


@router.post("/audit/auth-events")
async def auth_events() -> dict[str, int]:
    return {"imported": await import_auth_events(engine())}
