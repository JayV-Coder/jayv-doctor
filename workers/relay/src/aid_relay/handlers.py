"""Rodada do relay, chamada pelo Cloud Scheduler a cada minuto (POST /relay, com OIDC)."""

import os
from functools import lru_cache
from typing import Any

from aid_db import platform_role, supavisor_engine
from aid_observability.health import evaluate
from fastapi import APIRouter
from sqlalchemy import text
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


# Status interno para os operadores da plataforma (#34), fora da API dos tenants: o relay só
# aceita chamada com o IAM (`run.invoker`), dado no Terraform ao grupo de operadores. Só números
# de todas as Organizações juntas; os limites são os dos alertas.
@router.get("/admin/health")
async def admin_health() -> dict[str, Any]:
    async with engine().begin() as connection:
        await platform_role(connection)
        measures = await connection.scalar(text("select doctor.platform_health()"))
    return evaluate(dict(measures or {}))
