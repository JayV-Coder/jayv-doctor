"""Regras sobre a Execução fechada (`rules.evaluate`) e abertura de Incidentes.

Os matches são gravados com a versão da Regra. A Execução entra em um Incidente só, o da
categoria do match mais severo: o aberto (ou em análise) da mesma Integração e categoria cuja
janela de ocorrências, alargada em 30 min para cada lado, cruza a da Execução; senão, um novo.

Uma Execução pode ser avaliada de novo: reaberta por Eventos tardios, ou depois de absorver
outras (fusão). Cada avaliação refaz os matches da versão atual e tira a Execução (e as fundidas
nela) do Incidente em que estava antes de pô-la no certo. Um lock por Execução serializa as
entregas repetidas; os locks por Integração e categoria, tomados todos de uma vez e em ordem,
evitam dois Incidentes abertos para a mesma assinatura sem risco de deadlock.
"""

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from aid_db import platform_role
from aid_diagnosis_engine import rules
from aid_diagnosis_engine.incidents import incident_severity, incident_title, primary
from aid_diagnosis_engine.rules import EventView, ExecutionView, RuleMatch, evaluate
from aid_diagnosis_engine.rules.base import SEVERITIES
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

WINDOW = timedelta(minutes=30)
# Resolvido há menos que isto, com a mesma assinatura, é reaberto em vez de abrir outro.
REOPEN = timedelta(hours=24)


async def load(connection: AsyncConnection, execution_id: str) -> tuple[Any, list[EventView]]:
    execution = (
        await connection.execute(
            text(
                "select x.id::text, x.tenant_id::text, x.integration_id::text, x.status,"
                " x.first_event_at, x.last_event_at, x.closed_at, i.name, i.environment"
                " from doctor.executions x join doctor.integrations i"
                " on i.tenant_id = x.tenant_id and i.id = x.integration_id"
                # Só fechada e não fundida: a aberta será avaliada quando fechar de novo, e a
                # fundida, pela sobrevivente.
                " where x.id = cast(:x as uuid) and x.merged_into is null"
                " and x.closed_at is not null"
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
            # O intervalo da Execução leva o Postgres só às partições dela.
            " and timestamp between :first and :last"
        ),
        {
            "t": execution.tenant_id,
            "x": execution_id,
            "first": execution.first_event_at,
            "last": execution.last_event_at,
        },
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


async def unreconciled(connection: AsyncConnection, execution: Any) -> tuple[str, ...]:
    """Eventos da origem da Integração cuja chave de um Mapa com `reconcile` não aparece em
    nenhum Evento do destino nesta Execução (INT-008, #40). Só conta o Evento da origem mais
    antigo que a janela do Mapa: antes disso o destino pode estar a caminho. A varredura
    `reconcile_due` (worker de correlação) pede a avaliação de novo quando a janela passa, e o
    destino que chegar depois reabre a Execução e refaz o match."""
    rows = await connection.execute(
        text(
            "with maps as (select m.id::text as id, m.window_minutes"
            "  from doctor.correlation_mappings m"
            "  where m.tenant_id = cast(:t as uuid) and m.integration_id = cast(:i as uuid)"
            "  and m.reconcile),"
            " seen as (select e.id::text as event, e.timestamp as at,"
            "  e.source ->> 'provider' as system, k.key, maps.window_minutes"
            "  from doctor.events e cross join lateral unnest(e.cross_keys) as k(key)"
            "  join maps on k.key like maps.id || ':%'"
            "  where e.tenant_id = cast(:t as uuid) and e.execution_ref = cast(:x as uuid)"
            "  and e.timestamp between :first and :last and e.cross_keys is not null)"
            " select distinct s.event from seen s"
            " join doctor.integrations g on g.tenant_id = cast(:t as uuid)"
            " and g.id = cast(:i as uuid)"
            " where s.system = g.source_system and g.target_system <> g.source_system"
            " and s.at < now() - make_interval(mins => s.window_minutes)"
            " and not exists (select 1 from seen d where d.key = s.key"
            "  and d.system = g.target_system)"
            " order by 1"
        ),
        {
            "t": execution.tenant_id,
            "i": execution.integration_id,
            "x": execution.id,
            "first": execution.first_event_at,
            "last": execution.last_event_at,
        },
    )
    return tuple(row[0] for row in rows)


async def save_matches(
    connection: AsyncConnection, tenant: str, execution_id: str, matches: list[RuleMatch]
) -> None:
    """Refaz os matches das versões em vigor; os de versões antigas ficam (rastreabilidade)."""
    await connection.execute(
        text(
            "delete from doctor.rule_matches where tenant_id = cast(:t as uuid)"
            " and execution_id = cast(:x as uuid) and rule_version = any(cast(:v as text[]))"
        ),
        {"t": tenant, "x": execution_id, "v": sorted({item.version for item in rules.RULES})},
    )
    if not matches:
        return
    await connection.execute(
        text(
            "insert into doctor.rule_matches (tenant_id, execution_id, rule_code, rule_version,"
            " matched_event_ids, details) values (cast(:t as uuid), cast(:x as uuid), :c, :v,"
            " cast(:e as uuid[]), cast(:d as jsonb))"
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


async def previous_links(connection: AsyncConnection, execution: Any) -> list[Any]:
    """Ligações da Execução e das fundidas nela a Incidentes, com a categoria de cada um."""
    return list(
        await connection.execute(
            text(
                "select ie.incident_id::text as incident_id, ie.execution_id::text as execution_id,"
                " i.category, i.status from doctor.incident_executions ie join doctor.incidents i"
                " on i.tenant_id = ie.tenant_id and i.id = ie.incident_id"
                " where ie.tenant_id = cast(:t as uuid) and ie.execution_id in ("
                "  select id from doctor.executions where tenant_id = cast(:t as uuid)"
                "  and (id = cast(:x as uuid) or merged_into = cast(:x as uuid)))"
            ),
            {"t": execution.tenant_id, "x": execution.id},
        )
    )


async def detach(connection: AsyncConnection, tenant: str, links: list[Any]) -> None:
    for link in links:
        await connection.execute(
            text(
                "delete from doctor.incident_executions where tenant_id = cast(:t as uuid)"
                " and incident_id = cast(:i as uuid) and execution_id = cast(:x as uuid)"
            ),
            {"t": tenant, "i": link.incident_id, "x": link.execution_id},
        )
        await connection.execute(
            text(
                "update doctor.incidents set execution_count = greatest(execution_count - 1, 0)"
                " where tenant_id = cast(:t as uuid) and id = cast(:i as uuid)"
            ),
            {"t": tenant, "i": link.incident_id},
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


async def lock(connection: AsyncConnection, key: str) -> None:
    await connection.execute(
        text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key}
    )


async def reopen(connection: AsyncConnection, execution: Any, found: RuleMatch) -> Any:
    """Incidente resolvido com a mesma assinatura volta a `open` (ticket #20), com a reabertura no
    histórico, em vez de nascer outro, quando a Execução começou depois da resolução e até 24 h
    depois dela. Execução de antes da correção (Importação antiga, fechamento atrasado) não
    reabre nada: o tempo que conta é o dos Eventos, não o relógio."""
    resolved = (
        await connection.execute(
            text(
                "select id::text, severity, execution_count from doctor.incidents"
                " where tenant_id = cast(:t as uuid) and integration_id = cast(:i as uuid)"
                " and category = :c and status = 'resolved'"
                " and resolved_at < :first"
                " and :first <= resolved_at + make_interval(secs => :reopen)"
                " order by resolved_at desc limit 1 for update"
            ),
            {
                "t": execution.tenant_id,
                "i": execution.integration_id,
                "c": found.category,
                "first": execution.first_event_at,
                "reopen": REOPEN.total_seconds(),
            },
        )
    ).first()
    if resolved is None:
        return None
    await connection.execute(
        text(
            "update doctor.incidents set status = 'open'"
            " where tenant_id = cast(:t as uuid) and id = cast(:id as uuid)"
        ),
        {"t": execution.tenant_id, "id": resolved.id},
    )
    await connection.execute(
        text(
            "insert into doctor.incident_history (tenant_id, incident_id, action, from_value,"
            " to_value, note) values (cast(:t as uuid), cast(:id as uuid), 'reopened',"
            " 'resolved', 'open', 'Nova Execução com a mesma assinatura em até 24 h.')"
        ),
        {"t": execution.tenant_id, "id": resolved.id},
    )
    return resolved


async def attach(connection: AsyncConnection, execution: Any, found: RuleMatch) -> str:
    """Põe a Execução no Incidente certo (já sem ligação nenhuma); devolve o id dele."""
    tenant = execution.tenant_id
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
        current = await reopen(connection, execution, found)
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
    """Devolve o Incidente em que a Execução ficou, ou None (sem match, aberta ou fundida)."""
    target = str(payload["execution_id"])
    async with engine.begin() as connection:
        await platform_role(connection)
        await lock(connection, f"doctor.rules:{target}")
        execution, events = await load(connection, target)
        if execution is None:
            return None
        view = ExecutionView(
            id=execution.id,
            integration_id=execution.integration_id,
            status=execution.status,
            first_event_at=execution.first_event_at,
            last_event_at=execution.last_event_at,
            evaluated_at=execution.closed_at or datetime.now(UTC),
            unreconciled=await unreconciled(connection, execution),
        )
        matches = evaluate(view, events)
        await save_matches(connection, execution.tenant_id, execution.id, matches)
        found = primary(matches)
        links = await previous_links(connection, execution)
        # Já contada num Incidente resolvido ou descartado: a reavaliação não mexe nele (nem o
        # reabre). Só ligações a Incidentes ativos são refeitas.
        closed = [
            link
            for link in links
            if link.execution_id == execution.id and link.status in ("resolved", "dismissed")
        ]
        if closed:
            return str(closed[0].incident_id)
        links = [link for link in links if link.status in ("open", "investigating")]
        categories = {link.category for link in links} | ({found.category} if found else set())
        for category in sorted(categories):
            await lock(connection, f"doctor.incident:{execution.integration_id}:{category}")
        await detach(connection, execution.tenant_id, links)
        incident = await attach(connection, execution, found) if found else None
        for left in sorted({link.incident_id for link in links} - {incident}):
            await outbox(
                connection,
                execution.tenant_id,
                "incident.updated",
                {"incident_id": left, "execution_id": execution.id},
            )
        return incident
