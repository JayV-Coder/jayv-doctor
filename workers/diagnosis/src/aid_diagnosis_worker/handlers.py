"""Tópicos do worker de diagnóstico. As dependências saem do ambiente do Cloud Run."""

import os
from collections.abc import Awaitable, Callable, Mapping
from functools import lru_cache
from typing import Any

import httpx
from aid_db import supavisor_engine
from aid_diagnosis_engine.llm.registry import provider_for
from aid_knowledge.storage import KnowledgeStore
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_diagnosis_worker.backup import GcsTarget, StorageSource, backup_storage
from aid_diagnosis_worker.diagnose import diagnose, open_automatic
from aid_diagnosis_worker.evaluate import evaluate_execution
from aid_diagnosis_worker.knowledge import index, reindex_stale
from aid_diagnosis_worker.notify import mailer_from_env, notify_threshold
from aid_diagnosis_worker.report import generate_report
from aid_diagnosis_worker.retention import SupabaseStorage, run_retention

Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


@lru_cache
def engine() -> AsyncEngine:
    return supavisor_engine(os.environ["SUPABASE_DB_URL"])


@lru_cache
def store() -> KnowledgeStore:
    return KnowledgeStore(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


async def knowledge_index(payload: Mapping[str, Any]) -> None:
    await index(engine(), payload, store(), provider_for)


@lru_cache
def storage() -> SupabaseStorage:
    return SupabaseStorage(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


async def report_requested(payload: Mapping[str, Any]) -> None:
    await generate_report(engine(), payload, storage())


async def usage_threshold(payload: Mapping[str, Any]) -> None:
    await notify_threshold(engine(), payload, mailer_from_env())


async def rules_evaluate(payload: Mapping[str, Any]) -> None:
    await evaluate_execution(engine(), payload)


async def diagnosis_requested(payload: Mapping[str, Any]) -> None:
    await diagnose(engine(), payload, provider_for)


async def incident_opened(payload: Mapping[str, Any]) -> None:
    await open_automatic(engine(), payload)


async def no_consumer_yet(payload: Mapping[str, Any]) -> None:
    """`incident.updated` e `diagnosis.published` já saem, mas quem os consome chega com os
    alertas (v0.3). Até lá, confirmar evita reentrega e DLQ."""


TOPICS: dict[str, Handler] = {
    "rules.evaluate": rules_evaluate,
    "knowledge.index": knowledge_index,
    "diagnosis.requested": diagnosis_requested,
    "incident.opened": incident_opened,
    "incident.updated": no_consumer_yet,
    "diagnosis.published": no_consumer_yet,
    "usage.threshold": usage_threshold,
    "report.requested": report_requested,
}

router = APIRouter()


@router.post("/knowledge/reindex")
async def reindex() -> dict[str, int]:
    return {"queued": await reindex_stale(engine(), provider_for)}


@router.post("/retention/run")
async def retention() -> dict[str, int]:
    return await run_retention(engine(), storage())


@router.post("/backup/storage")
async def storage_backup() -> dict[str, int]:
    # Um cliente HTTP para a rodada inteira (conexões reaproveitadas), fechado no fim.
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        source = StorageSource(
            os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"], client
        )
        target = GcsTarget(os.environ["BACKUP_BUCKET"], client)
        return await backup_storage(engine(), source, target)
