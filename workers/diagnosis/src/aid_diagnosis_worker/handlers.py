"""Tópicos do worker de diagnóstico. As dependências saem do ambiente do Cloud Run."""

import os
from collections.abc import Awaitable, Callable, Mapping
from functools import lru_cache
from typing import Any

from aid_db import supavisor_engine
from aid_diagnosis_engine.llm.registry import provider_for
from aid_knowledge.storage import KnowledgeStore
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_diagnosis_worker.evaluate import evaluate_execution
from aid_diagnosis_worker.knowledge import index, reindex_stale

Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


@lru_cache
def engine() -> AsyncEngine:
    return supavisor_engine(os.environ["SUPABASE_DB_URL"])


@lru_cache
def store() -> KnowledgeStore:
    return KnowledgeStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


async def knowledge_index(payload: Mapping[str, Any]) -> None:
    await index(engine(), payload, store(), provider_for)


async def rules_evaluate(payload: Mapping[str, Any]) -> None:
    await evaluate_execution(engine(), payload)


async def no_consumer_yet(payload: Mapping[str, Any]) -> None:
    """`incident.opened`/`incident.updated` já saem (ticket #18), mas quem os consome chega com o
    Diagnóstico (#24) e os alertas (v0.3). Até lá, confirmar evita reentrega e DLQ."""


TOPICS: dict[str, Handler] = {
    "rules.evaluate": rules_evaluate,
    "knowledge.index": knowledge_index,
    "incident.opened": no_consumer_yet,
    "incident.updated": no_consumer_yet,
}

router = APIRouter()


@router.post("/knowledge/reindex")
async def reindex() -> dict[str, int]:
    return {"queued": await reindex_stale(engine(), provider_for)}
