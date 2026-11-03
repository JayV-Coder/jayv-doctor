"""Drena a outbox: publica as mensagens pendentes e marca `published_at`.

`FOR UPDATE SKIP LOCKED` deixa dois relays rodarem juntos sem publicar a mesma linha. Cada lote
sai numa chamada por tópico, com um cliente HTTP só, e a rodada para antes do prazo do Cloud Run.
A entrega é pelo menos uma vez: se o commit falhar depois do publish, a mensagem sai de novo, e
os consumidores são idempotentes.

Só a recusa do Pub/Sub (tópico inexistente, pedido inválido) conta tentativa. Falha do próprio
relay ou do Pub/Sub encerra a rodada sem gastar tentativa de ninguém: uma queda de 10 minutos não
abandona as mensagens. Mensagem recusada 10 vezes fica na tabela para investigação.
"""

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_relay.publisher import Message, PublishError, PubSubPublisher

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 10
# Abaixo dos 60 s do Cloud Run e do Scheduler, com folga para o último lote.
ROUND_SECONDS = 40.0


@dataclass
class Stats:
    published: int = 0
    failed: int = 0
    stopped: bool = False


async def mark(connection: AsyncConnection, published: list[int], rejected: list[int]) -> None:
    if published:
        await connection.execute(
            text("update doctor.outbox_messages set published_at = now() where id = any(:ids)"),
            {"ids": published},
        )
    if rejected:
        await connection.execute(
            text("update doctor.outbox_messages set attempts = attempts + 1 where id = any(:ids)"),
            {"ids": rejected},
        )


async def publish_batch(
    client: httpx.AsyncClient, publisher: PubSubPublisher, rows: list[Any], stats: Stats
) -> tuple[list[int], list[int]]:
    by_topic: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        by_topic[row.topic].append(row)
    published: list[int] = []
    rejected: list[int] = []
    for topic, items in by_topic.items():
        messages: list[Message] = [
            (
                json.dumps(row.payload).encode(),
                {"tenant_id": row.tenant_id, "outbox_id": str(row.id)},
            )
            for row in items
        ]
        try:
            await publisher.publish(client, topic, messages)
        except PublishError as exc:
            # Só identificadores e o motivo no log: o payload pode citar dados do cliente.
            logger.warning("outbox: %s (%d mensagens)", exc, len(items))
            if not exc.rejected:
                stats.stopped = True
                break
            rejected.extend(row.id for row in items)
        except Exception:
            logger.exception("outbox: erro inesperado ao publicar em %s", topic)
            stats.stopped = True
            break
        else:
            published.extend(row.id for row in items)
    return published, rejected


async def drain(
    engine: AsyncEngine,
    publisher: PubSubPublisher,
    *,
    batch: int = 100,
    seconds: float = ROUND_SECONDS,
) -> Stats:
    stats = Stats()
    deadline = time.monotonic() + seconds
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        while time.monotonic() < deadline and not stats.stopped:
            async with engine.begin() as connection:
                await connection.execute(text("set local role service_role"))
                rows = (
                    await connection.execute(
                        text(
                            "select id, tenant_id::text, topic, payload"
                            " from doctor.outbox_messages"
                            " where published_at is null and attempts < :max"
                            " order by id limit :batch for update skip locked"
                        ),
                        {"max": MAX_ATTEMPTS, "batch": batch},
                    )
                ).all()
                if not rows:
                    break
                published, rejected = await publish_batch(client, publisher, list(rows), stats)
                await mark(connection, published, rejected)
            stats.published += len(published)
            stats.failed += len(rejected)
            if len(rows) < batch:
                break
    return stats
