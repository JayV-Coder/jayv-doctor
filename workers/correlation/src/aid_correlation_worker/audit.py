"""Job diário da Trilha de auditoria (#28): copia login, logout e MFA do Supabase Auth para as
Organizações de cada Usuário e cria as partições mensais dos próximos meses."""

from datetime import UTC, date, datetime, timedelta

from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# Primeira rodada (ou depois de uma parada longa): não vai mais longe que isto.
LOOKBACK = timedelta(days=2)
MONTHS_AHEAD = 2


def next_months(today: date, count: int = MONTHS_AHEAD) -> list[date]:
    months, current = [], today.replace(day=1)
    for _ in range(count + 1):
        months.append(current)
        current = (current + timedelta(days=32)).replace(day=1)
    return months


async def import_auth_events(engine: AsyncEngine, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    async with engine.begin() as connection:
        await platform_role(connection)
        last = await connection.scalar(
            text("select max(occurred_at) from doctor.audit_logs where action like 'auth.%'")
        )
        since = max(last, now - LOOKBACK) if last else now - LOOKBACK
        for month in next_months(now.date()):
            await connection.execute(text("select doctor.ensure_audit_partition(:m)"), {"m": month})
        imported = await connection.scalar(
            text("select doctor.import_auth_events(:since)"), {"since": since}
        )
    return int(imported or 0)
