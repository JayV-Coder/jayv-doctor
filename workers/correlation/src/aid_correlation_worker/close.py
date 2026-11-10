"""Fechamento: o Cloud Scheduler chama POST /close a cada minuto. Execução sem mudança há 5 min
fecha com o status final de `aid_correlation.final_status` e pede a avaliação das Regras
(`rules.evaluate`, ticket #18). Execução fundida em outra já nasce fechada e não entra."""

import json
from datetime import timedelta

from aid_correlation import final_status
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

IDLE = timedelta(minutes=5)
BATCH = 500


async def close_idle(engine: AsyncEngine, idle: timedelta = IDLE) -> int:
    async with engine.begin() as connection:
        await platform_role(connection)
        due = list(
            await connection.execute(
                text(
                    "select id::text, tenant_id::text, integration_id::text, status,"
                    " low_confidence from doctor.executions"
                    " where closed_at is null and merged_into is null"
                    " and last_activity_at <= now() - make_interval(secs => :idle)"
                    " order by last_activity_at limit :batch for update skip locked"
                ),
                {"idle": idle.total_seconds(), "batch": BATCH},
            )
        )
        if not due:
            return 0
        await connection.execute(
            text(
                "update doctor.executions set closed_at = now(), status = :s"
                " where tenant_id = cast(:t as uuid) and id = cast(:x as uuid)"
            ),
            [
                {
                    "t": row.tenant_id,
                    "x": row.id,
                    "s": final_status(
                        failed=row.status == "failed",
                        low_confidence=row.low_confidence,
                        closed=True,
                    ),
                }
                for row in due
            ],
        )
        await connection.execute(
            text(
                "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                " values (cast(:t as uuid), 'rules.evaluate', cast(:p as jsonb))"
            ),
            [
                {
                    "t": row.tenant_id,
                    "p": json.dumps({"execution_id": row.id, "integration_id": row.integration_id}),
                }
                for row in due
            ],
        )
        return len(due)


async def reconcile_due(engine: AsyncEngine) -> int:
    """Divergência pelo Mapa (INT-008, #40): a Execução fechada de uma Integração com Mapa de
    `reconcile` é avaliada de novo quando a maior janela desses Mapas já passou desde o último
    Evento. Antes disso, a ausência do destino não prova nada (ele pode chegar em lote)."""
    async with engine.begin() as connection:
        await platform_role(connection)
        due = list(
            await connection.execute(
                text(
                    "with due as ("
                    " select x.id, x.tenant_id, x.integration_id from doctor.executions x"
                    " join lateral (select max(m.window_minutes) as window"
                    "  from doctor.correlation_mappings m where m.tenant_id = x.tenant_id"
                    "  and m.integration_id = x.integration_id and m.reconcile) r on true"
                    " where x.reconciled_at is null and x.closed_at is not null"
                    " and x.merged_into is null and r.window is not null"
                    " and x.last_event_at < now() - make_interval(mins => r.window)"
                    " order by x.last_event_at limit :batch for update of x skip locked)"
                    " update doctor.executions x set reconciled_at = now() from due"
                    " where x.id = due.id"
                    " returning x.id::text, x.tenant_id::text, x.integration_id::text"
                ),
                {"batch": BATCH},
            )
        )
        if due:
            await connection.execute(
                text(
                    "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                    " values (cast(:t as uuid), 'rules.evaluate', cast(:p as jsonb))"
                ),
                [
                    {
                        "t": row.tenant_id,
                        "p": json.dumps(
                            {"execution_id": row.id, "integration_id": row.integration_id}
                        ),
                    }
                    for row in due
                ],
            )
        return len(due)
