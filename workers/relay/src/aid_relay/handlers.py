"""Rodada do relay, chamada pelo Cloud Scheduler a cada minuto (POST /relay, com OIDC)."""

import os
from functools import lru_cache

from aid_db import supavisor_engine
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_relay.publisher import PubSubPublisher
from aid_relay.relay import drain


@lru_cache
def engine() -> AsyncEngine:
    return supavisor_engine(os.environ["SUPABASE_DB_URL"])


@lru_cache
def publisher() -> PubSubPublisher:
    return PubSubPublisher(
        os.environ["GCP_PROJECT_ID"], emulator_host=os.environ.get("PUBSUB_EMULATOR_HOST")
    )


router = APIRouter()


# Disparado pelo Cloud Scheduler: sempre 200, a próxima rodada retoma o que faltou.
@router.post("/relay")
async def relay() -> dict[str, int]:
    stats = await drain(engine(), publisher())
    return {"published": stats.published, "failed": stats.failed}
