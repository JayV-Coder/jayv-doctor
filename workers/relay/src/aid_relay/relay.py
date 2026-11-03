"""Drena a outbox: publica as mensagens pendentes e marca `published_at`.

`FOR UPDATE SKIP LOCKED` deixa dois relays rodarem juntos sem publicar a mesma linha. A entrega é
pelo menos uma vez: se o commit falhar depois do publish, a mensagem sai de novo, e os
consumidores são idempotentes. Mensagem que falhou 10 vezes para de ser tentada e fica na tabela
para investigação (a métrica de lag da outbox a mostra).
"""

import json
import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_relay.publisher import PublishError, PubSubPublisher

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 10


@dataclass
class Stats:
    published: int = 0
    failed: int = 0


async def drain(
    engine: AsyncEngine, publisher: PubSubPublisher, *, batch: int = 100, max_batches: int = 20
) -> Stats:
    stats = Stats()
    for _ in range(max_batches):
        async with engine.begin() as connection:
            await connection.execute(text("set local role service_role"))
            rows = (
                await connection.execute(
                    text(
                        "select id, tenant_id::text, topic, payload from doctor.outbox_messages"
                        " where published_at is null and attempts < :max"
                        " order by id limit :batch for update skip locked"
                    ),
                    {"max": MAX_ATTEMPTS, "batch": batch},
                )
            ).all()
            if not rows:
                break
            published, failed = [], []
            for row in rows:
                try:
                    await publisher.publish(
                        row.topic,
                        json.dumps(row.payload).encode(),
                        {"tenant_id": row.tenant_id, "outbox_id": str(row.id)},
                    )
                except PublishError:
                    # Só identificadores no log: o payload pode citar dados do cliente.
                    logger.warning("outbox: falha ao publicar id=%s topic=%s", row.id, row.topic)
                    failed.append(row.id)
                else:
                    published.append(row.id)
            if published:
                await connection.execute(
                    text(
                        "update doctor.outbox_messages set published_at = now()"
                        " where id = any(:ids)"
                    ),
                    {"ids": published},
                )
            if failed:
                await connection.execute(
                    text(
                        "update doctor.outbox_messages set attempts = attempts + 1"
                        " where id = any(:ids)"
                    ),
                    {"ids": failed},
                )
            stats.published += len(published)
            stats.failed += len(failed)
        if len(rows) < batch:
            break
    return stats
