"""Agregado do Dashboard (ticket #21): o Cloud Scheduler chama POST /stats a cada 10 min (o
pg_cron do projeto é do jayv-coder). Cada rodada drena a fila de horas que triggers do banco
anotaram (`execution_stats_dirty`) e as recalcula; uma rodada que falhar deixa a fila para a
seguinte, sem perder nada."""

from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

BATCH = 5000


async def refresh_stats(engine: AsyncEngine) -> int:
    total = 0
    while True:
        async with engine.begin() as connection:
            await platform_role(connection)
            done = int(
                await connection.scalar(
                    text("select doctor.refresh_execution_stats(:b)"), {"b": BATCH}
                )
                or 0
            )
        total += done
        if done < BATCH:
            return total
