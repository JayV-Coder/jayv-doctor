"""Fechamento: o Cloud Scheduler chama POST /close a cada minuto. Execução sem mudança há 5 min
fecha com o status final e pede a avaliação das Regras (`rules.evaluate`, ticket #18).

O status final segue `aid_correlation.execution_status`: com erro, `failed`; agrupada só por
proximidade (ou sem estratégia), `unknown`; senão, `success`."""

from datetime import timedelta

from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

IDLE = timedelta(minutes=5)
BATCH = 500


async def close_idle(engine: AsyncEngine, idle: timedelta = IDLE) -> int:
    async with engine.begin() as connection:
        await platform_role(connection)
        result = await connection.execute(
            text(
                "with due as ("
                " select id from doctor.executions"
                " where closed_at is null"
                " and last_activity_at <= now() - make_interval(secs => :idle)"
                " order by last_activity_at limit :batch for update skip locked),"
                " closed as ("
                " update doctor.executions x set closed_at = now(),"
                "  status = case when x.status = 'failed' then 'failed'"
                "   when x.low_confidence then 'unknown' else 'success' end"
                " from due where x.id = due.id"
                " returning x.id, x.tenant_id, x.integration_id)"
                " insert into doctor.outbox_messages (tenant_id, topic, payload)"
                " select tenant_id, 'rules.evaluate',"
                "  jsonb_build_object('execution_id', id, 'integration_id', integration_id)"
                " from closed"
            ),
            {"idle": idle.total_seconds(), "batch": BATCH},
        )
        return result.rowcount or 0
