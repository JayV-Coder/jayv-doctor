"""Tópico `connector.sync` e rota do agendador do worker de Conectores."""

import os
from collections.abc import Awaitable, Callable, Mapping
from functools import lru_cache
from typing import Any

from aid_connectors.runtime import RetryPolicy
from aid_db import supavisor_engine
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_connector_worker.schedule import enqueue_due
from aid_connector_worker.sync import REGISTRY, sync_connector

Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


@lru_cache
def engine() -> AsyncEngine:
    return supavisor_engine(os.environ["SUPABASE_DB_URL"])


async def connector_sync(payload: Mapping[str, Any]) -> None:
    # `busy`: outra Sincronização do mesmo Conector está em curso; esta mensagem é descartada e o
    # agendador enfileira de novo no próximo vencimento.
    await sync_connector(payload, engine(), REGISTRY, RetryPolicy())


TOPICS: dict[str, Handler] = {"connector.sync": connector_sync}

router = APIRouter()


@router.post("/schedule")
async def schedule() -> dict[str, int]:
    return {"queued": await enqueue_due(engine())}
