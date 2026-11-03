"""Tópicos do worker de diagnóstico. As dependências saem do ambiente do Cloud Run."""

import os
from collections.abc import Awaitable, Callable, Mapping
from functools import lru_cache
from typing import Any

from aid_db import supavisor_engine
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_diagnosis_worker.evaluate import evaluate_execution

Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


@lru_cache
def engine() -> AsyncEngine:
    return supavisor_engine(os.environ["SUPABASE_DB_URL"])


async def rules_evaluate(payload: Mapping[str, Any]) -> None:
    await evaluate_execution(engine(), payload)


async def no_consumer_yet(payload: Mapping[str, Any]) -> None:
    """`incident.opened`/`incident.updated` já saem (ticket #18), mas quem os consome chega com o
    Diagnóstico (#24) e os alertas (v0.3). Até lá, confirmar evita reentrega e DLQ."""


TOPICS: dict[str, Handler] = {
    "rules.evaluate": rules_evaluate,
    "incident.opened": no_consumer_yet,
    "incident.updated": no_consumer_yet,
}
