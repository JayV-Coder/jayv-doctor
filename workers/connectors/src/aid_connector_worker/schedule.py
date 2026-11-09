"""Agendador: o Cloud Scheduler chama POST /schedule a cada minuto (o pg_cron do projeto é do
jayv-coder). Cada Conector vencido ganha uma mensagem `connector.sync` na outbox e passa a vencer
de novo só depois do intervalo dele: a fila não recebe o mesmo Conector a cada minuto."""

from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

BATCH = 200


async def enqueue_due(engine: AsyncEngine) -> int:
    async with engine.begin() as connection:
        await platform_role(connection)
        # Pausado pelo limite diário do provedor (#37): passada a janela, volta à fila.
        await connection.execute(
            text(
                "update doctor.connectors set status = 'active', paused_reason = null"
                " where status = 'paused' and paused_reason = 'api_limit'"
                " and next_run_at <= now()"
            )
        )
        result = await connection.execute(
            text(
                "with due as ("
                " select id, tenant_id from doctor.connectors"
                " where status in ('active', 'failing') and next_run_at <= now()"
                " order by next_run_at limit :batch for update skip locked),"
                " bumped as ("
                " update doctor.connectors c"
                " set next_run_at = now() + make_interval(secs => c.sync_interval_seconds)"
                " from due where c.id = due.id returning c.id, c.tenant_id)"
                " insert into doctor.outbox_messages (tenant_id, topic, payload)"
                " select tenant_id, 'connector.sync', jsonb_build_object('connector_id', id)"
                " from bumped"
            ),
            {"batch": BATCH},
        )
        return result.rowcount or 0
