"""Regras sobre a Execução fechada (`rules.evaluate`) e abertura de Incidentes.

Os matches são gravados com a versão da Regra. A Execução entra em um Incidente só, o da
categoria do match mais severo: o aberto (ou em análise) da mesma Integração e categoria cuja
janela de ocorrências, alargada em 30 min para cada lado, cruza a da Execução; senão, um novo.
Um lock por Integração e categoria evita dois Incidentes abertos ao mesmo tempo para a mesma
assinatura. A mensagem repetida não duplica nada (uniques de match e de Execução no Incidente).
"""

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from aid_db import platform_role
from aid_diagnosis_engine.incidents import incident_severity, incident_title, primary
from aid_diagnosis_engine.rules import EventView, ExecutionView, RuleMatch, evaluate
from aid_diagnosis_engine.rules.base import SEVERITIES
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

WINDOW = timedelta(minutes=30)


async def load(connection: AsyncConnection, execution_id: str) -> tuple[Any, list[EventView]]:
    execution = (
        await connection.execute(
            text(
                "select x.id::text, x.tenant_id::text, x.integration_id::text, x.status,"
                " x.first_event_at, x.last_event_at, x.closed_at, i.name, i.environment"
                " from doctor.executions x join doctor.integrations i"
                " on i.tenant_id = x.tenant_id and i.id = x.integration_id"
                " where x.id = cast(:x as uuid) and x.merged_into is null"
            ),
            {"x": execution_id},
        )
    ).first()
    if execution is None:
        return None, []
    rows = await connection.execute(
        text(
            "select id::text, timestamp, severity, operation, error, attributes"
            " from doctor.events where tenant_id = cast(:t as uuid)"
            " and execution_ref = cast(:x as uuid)"
        ),
        {"t": execution.tenant_id, "x": execution_id},
    )
    events = [
        EventView(
            id=row.id,
            timestamp=row.timestamp,
            severity=row.severity,
            operation=row.operation,
            error=row.error,
            attributes=row.attributes or {},
        )
        for row in rows
    ]
    return execution, events


async def save_matches(
    connection: AsyncConnection, tenant: str, execution_id: str, matches: list[RuleMatch]
) -> None:
    if not matches:
        return
    await connection.execute(
        text(
            "insert into doctor.rule_matches (tenant_id, execution_id, rule_code, rule_version,"
            " matched_event_ids, details) values (cast(:t as uuid), cast(:x as uuid), :c, :v,"
            " cast(:e as uuid[]), cast(:d as jsonb)) on conflict do nothing"
        ),
        [
            {
                "t": tenant,
                "x": execution_id,
                "c": found.rule_code,
                "v": found.rule_version,
                "e": list(found.matched_event_ids),
                "d": json.dumps(found.details),
            }
            for found in matches
        ],
    )


async def outbox(
    connection: AsyncConnection, tenant: str, topic: str, payload: dict[str, Any]
) -> None:
    await connection.execute(
        text(
            "insert into doctor.outbox_messages (tenant_id, topic, payload)"
            " values (cast(:t as uuid), :topic, cast(:p as jsonb))"
        ),
        {"t": tenant, "topic": topic, "p": json.dumps(payload)},
    )


async def attach(connection: AsyncConnection, execution: Any, found: RuleMatch) -> str:
    """Põe a Execução no Incidente certo; devolve o id dele."""
    tenant = execution.tenant_id
    linked = await connection.scalar(
        text(
            "select incident_id::text from doctor.incident_executions"
            " where tenant_id = cast(:t as uuid) and execution_id = cast(:x as uuid)"
        ),
        {"t": tenant, "x": execution.id},
    )
    if linked:
        return str(linked)
    await connection.execute(
        text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"doctor.incident:{execution.integration_id}:{found.category}"},
    )
    current = (
        await connection.execute(
            text(
                "select id::text, severity, execution_count from doctor.incidents"
                " where tenant_id = cast(:t as uuid) and integration_id = cast(:i as uuid)"
                " and category = :c and status in ('open', 'investigating')"
                " and first_seen_at - make_interval(secs => :w) <= :last"
                " and last_seen_at + make_interval(secs => :w) >= :first"
                " order by last_seen_at desc limit 1 for update"
            ),
            {
                "t": tenant,
                "i": execution.integration_id,
                "c": found.category,
                "w": WINDOW.total_seconds(),
                "first": execution.first_event_at,
                "last": execution.last_event_at,
            },
        )
    ).first()
    if current is None:
        incident = str(
            await connection.scalar(
                text(
                    "insert into doctor.incidents (tenant_id, integration_id, title, category,"
                    " severity, rule_code, rule_version, first_seen_at, last_seen_at,"
                    " execution_count) values (cast(:t as uuid), cast(:i as uuid), :title, :c,"
                    " :s, :code, :v, :first, :last, 1) returning id::text"
                ),
                {
                    "t": tenant,
                    "i": execution.integration_id,
                    "title": incident_title(found.category, execution.name),
                    "c": found.category,
                    "s": incident_severity(found.severity_hint, execution.environment, 1),
                    "code": found.rule_code,
                    "v": found.rule_version,
                    "first": execution.first_event_at,
                    "last": execution.last_event_at,
                },
            )
        )
        topic = "incident.opened"
    else:
        incident = current.id
        count = current.execution_count + 1
        computed = incident_severity(found.severity_hint, execution.environment, count)
        # A severidade automática só sobe: quem baixou na mão (#20) não é desfeito por volume.
        severity = max(current.severity, computed, key=SEVERITIES.index)
        await connection.execute(
            text(
                "update doctor.incidents set execution_count = :n, severity = :s,"
                " first_seen_at = least(first_seen_at, :first),"
                " last_seen_at = greatest(last_seen_at, :last)"
                " where tenant_id = cast(:t as uuid) and id = cast(:id as uuid)"
            ),
            {
                "t": tenant,
                "id": incident,
                "n": count,
                "s": severity,
                "first": execution.first_event_at,
                "last": execution.last_event_at,
            },
        )
        topic = "incident.updated"
    await connection.execute(
        text(
            "insert into doctor.incident_executions (tenant_id, incident_id, execution_id)"
            " values (cast(:t as uuid), cast(:id as uuid), cast(:x as uuid))"
        ),
        {"t": tenant, "id": incident, "x": execution.id},
    )
    await outbox(connection, tenant, topic, {"incident_id": incident, "execution_id": execution.id})
    return incident


async def evaluate_execution(engine: AsyncEngine, payload: Mapping[str, Any]) -> str | None:
    """Devolve o Incidente em que a Execução entrou, ou None (sem match, ou Execução fundida)."""
    async with engine.begin() as connection:
        await platform_role(connection)
        execution, events = await load(connection, str(payload["execution_id"]))
        if execution is None:
            # Fundida em outra depois do fechamento: a sobrevivente será avaliada ao fechar.
            return None
        view = ExecutionView(
            id=execution.id,
            integration_id=execution.integration_id,
            status=execution.status,
            first_event_at=execution.first_event_at,
            last_event_at=execution.last_event_at,
            evaluated_at=execution.closed_at or datetime.now(UTC),
        )
        matches = evaluate(view, events)
        await save_matches(connection, execution.tenant_id, execution.id, matches)
        found = primary(matches)
        if found is None:
            return None
        return await attach(connection, execution, found)
