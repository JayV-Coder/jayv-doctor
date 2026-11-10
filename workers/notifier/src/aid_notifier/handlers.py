"""Tópico `alert.evaluate` e a varredura agendada do worker `notifier` (ticket #41)."""

import os
from collections.abc import Awaitable, Callable, Mapping
from functools import lru_cache
from typing import Any

from aid_db import supavisor_engine
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_notifier.channels import Senders
from aid_notifier.notify import evaluate, scan
from aid_notifier.webhooks import deliver, due

Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


@lru_cache
def engine() -> AsyncEngine:
    return supavisor_engine(os.environ["SUPABASE_DB_URL"])


async def alert_evaluate(payload: Mapping[str, Any]) -> None:
    await evaluate(engine(), payload, Senders())


async def webhook_deliver(payload: Mapping[str, Any]) -> None:
    await deliver(engine(), str(payload["delivery_id"]), Senders())


TOPICS: dict[str, Handler] = {"alert.evaluate": alert_evaluate, "webhook.deliver": webhook_deliver}

router = APIRouter()


# A cada minuto (Cloud Scheduler): taxa de erro, Diagnóstico aguardando revisão e as novas
# tentativas dos webhooks (#42).
@router.post("/alerts/scan")
async def alerts_scan() -> dict[str, int]:
    return {
        "sent": await scan(engine(), Senders()),
        "webhooks": await due(engine(), Senders()),
    }
