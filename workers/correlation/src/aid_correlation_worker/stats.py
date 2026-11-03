"""Agregado do Dashboard (ticket #21): o Cloud Scheduler chama POST /stats a cada 10 min (o
pg_cron do projeto é do jayv-coder). Cada rodada recalcula as horas tocadas desde a anterior,
com folga, então o atraso máximo do Dashboard fica bem abaixo de 1 h."""

from datetime import timedelta

from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# Duas rodadas e meia: uma rodada que falhar é coberta pela seguinte.
LOOKBACK = timedelta(minutes=25)


async def refresh_stats(engine: AsyncEngine, lookback: timedelta = LOOKBACK) -> int:
    async with engine.begin() as connection:
        await platform_role(connection)
        found = await connection.scalar(
            text("select doctor.refresh_execution_stats(now() - make_interval(secs => :s))"),
            {"s": lookback.total_seconds()},
        )
        return int(found or 0)
