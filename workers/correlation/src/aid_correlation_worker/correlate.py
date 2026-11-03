"""Correlação dos Eventos pendentes de uma Integração (`correlation.requested`).

Cada mensagem só diz qual Integração tem Eventos novos; o worker pega os pendentes
(`execution_ref` nulo), a vizinhança já correlacionada que pode se ligar a eles (mesmos ids,
Referência na janela, mesmo recurso na proximidade) e os demais Eventos dessas Execuções, e roda
o motor sobre o conjunto. Execuções nunca se dividem: as que o motor junta são fundidas na mais
antiga, com histórico em `execution_merges`. Um lock por Integração serializa as mensagens
concorrentes; a mensagem repetida não acha pendentes e termina sem efeito.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

from aid_correlation import Correlator, EventRef, Group, execution_status, merge_plan
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

# Pendentes por mensagem; com mais, a própria mensagem pede a continuação pela outbox.
PAGE = 2000

COLUMNS = (
    "e.id::text as id, e.tenant_id::text as tenant_id, e.integration_id::text as integration_id,"
    " e.timestamp, e.severity, e.operation, e.execution_id, e.trace_id, e.business_reference,"
    " e.source ->> 'resource' as resource,"
    " case when e.attributes ->> 'attempt' ~ '^[0-9]{1,6}$'"
    "  then (e.attributes ->> 'attempt')::int end as attempt,"
    " e.execution_ref::text as execution_ref"
)

PENDING = text(
    f"select {COLUMNS} from doctor.events e"  # noqa: S608
    " where e.tenant_id = cast(:t as uuid) and e.integration_id = cast(:i as uuid)"
    " and e.execution_ref is null order by e.timestamp, e.id limit :page"
)

NEIGHBORS = text(
    f"select {COLUMNS} from doctor.events e"  # noqa: S608
    " where e.tenant_id = cast(:t as uuid) and e.integration_id = cast(:i as uuid)"
    " and e.execution_ref is not null and ("
    "  e.execution_id = any(cast(:execs as text[])) or e.trace_id = any(cast(:traces as text[]))"
    "  or (e.business_reference = any(cast(:refs as text[]))"
    "   and e.timestamp between cast(:lo as timestamptz) - make_interval(secs => :window)"
    "   and cast(:hi as timestamptz) + make_interval(secs => :window))"
    "  or (e.source ->> 'resource' = any(cast(:resources as text[]))"
    "   and e.timestamp between cast(:lo as timestamptz) - make_interval(secs => :near)"
    "   and cast(:hi as timestamptz) + make_interval(secs => :near)))"
)

MEMBERS = text(
    f"select {COLUMNS} from doctor.events e"  # noqa: S608
    " where e.tenant_id = cast(:t as uuid) and e.execution_ref = any(cast(:refs as uuid[]))"
)


def to_ref(row: Row[Any]) -> EventRef:
    return EventRef(**row._asdict())


async def load(connection: AsyncConnection, query: Any, **params: Any) -> list[EventRef]:
    return [to_ref(row) for row in await connection.execute(query, params)]


async def tenant_of(connection: AsyncConnection, integration_id: str) -> str | None:
    found = await connection.scalar(
        text("select tenant_id::text from doctor.integrations where id = cast(:i as uuid)"),
        {"i": integration_id},
    )
    return str(found) if found else None


async def neighborhood(
    connection: AsyncConnection,
    tenant: str,
    integration: str,
    pending: Sequence[EventRef],
    correlator: Correlator,
) -> list[EventRef]:
    def values(name: str) -> list[str]:
        return sorted({str(getattr(e, name)) for e in pending if getattr(e, name) is not None})

    neighbors = await load(
        connection,
        NEIGHBORS,
        t=tenant,
        i=integration,
        execs=values("execution_id"),
        traces=values("trace_id"),
        refs=values("business_reference"),
        resources=values("resource"),
        lo=min(e.timestamp for e in pending),
        hi=max(e.timestamp for e in pending),
        window=correlator.settings.reference_window.total_seconds(),
        near=correlator.settings.proximity.total_seconds(),
    )
    refs = sorted({e.execution_ref for e in neighbors if e.execution_ref})
    members = await load(connection, MEMBERS, t=tenant, refs=refs) if refs else []
    return [*neighbors, *members]


async def existing(connection: AsyncConnection, tenant: str, refs: set[str]) -> dict[str, Any]:
    rows = await connection.execute(
        text(
            "select id::text, first_event_at, correlation_keys from doctor.executions"
            " where tenant_id = cast(:t as uuid) and id = any(cast(:ids as uuid[]))"
            " order by id for update"
        ),
        {"t": tenant, "ids": sorted(refs)},
    )
    return {row.id: row for row in rows}


async def resolve(connection: AsyncConnection, tenant: str, group: Group, refs: set[str]) -> str:
    """A Execução do grupo: nova, a que já existia, ou a mais antiga, com as outras fundidas."""
    found = await existing(connection, tenant, refs) if refs else {}
    survivor, merged = merge_plan(
        {key: row.first_event_at.isoformat() for key, row in found.items()}
    )
    if survivor is None:
        created = await connection.scalar(
            text(
                "insert into doctor.executions (tenant_id, integration_id, first_event_at,"
                " last_event_at) values (cast(:t as uuid), cast(:i as uuid), :f, :l)"
                " returning id::text"
            ),
            {
                "t": tenant,
                "i": group.integration_id,
                "f": group.first_event_at,
                "l": group.last_event_at,
            },
        )
        return str(created)
    for target in merged:
        await connection.execute(
            text(
                "insert into doctor.execution_merges"
                " (tenant_id, survivor_id, merged_id, merged_keys)"
                " values (cast(:t as uuid), cast(:s as uuid), cast(:m as uuid), cast(:k as jsonb))"
            ),
            {
                "t": tenant,
                "s": survivor,
                "m": target,
                "k": json.dumps(found[target].correlation_keys),
            },
        )
        await connection.execute(
            text(
                "update doctor.events set execution_ref = cast(:s as uuid)"
                " where tenant_id = cast(:t as uuid) and execution_ref = cast(:m as uuid)"
            ),
            {"t": tenant, "s": survivor, "m": target},
        )
        await connection.execute(
            text(
                "delete from doctor.executions"
                " where tenant_id = cast(:t as uuid) and id = cast(:m as uuid)"
            ),
            {"t": tenant, "m": target},
        )
    return survivor


async def assign(
    connection: AsyncConnection,
    tenant: str,
    execution: str,
    group: Group,
    pending: Mapping[str, EventRef],
) -> None:
    rows = [
        {
            "t": tenant,
            "id": event_id,
            "ts": pending[event_id].timestamp,
            "x": execution,
            "c": group.correlated_by.get(event_id),
        }
        for event_id in group.event_ids
        if event_id in pending
    ]
    # Com o instante na condição: o Postgres vai direto à partição do Evento.
    await connection.execute(
        text(
            "update doctor.events set execution_ref = cast(:x as uuid), correlated_by = :c"
            " where tenant_id = cast(:t as uuid) and id = cast(:id as uuid) and timestamp = :ts"
        ),
        rows,
    )


async def refresh(connection: AsyncConnection, tenant: str, execution: str, group: Group) -> None:
    """Os números saem do grupo inteiro; Evento novo reabre a Execução (fecha de novo em 5 min)."""
    await connection.execute(
        text(
            "update doctor.executions set first_event_at = :f, last_event_at = :l,"
            " duration_ms = :d, event_count = :n, correlation_keys = cast(:k as jsonb),"
            " low_confidence = :w, status = :s, last_activity_at = now(), closed_at = null"
            " where tenant_id = cast(:t as uuid) and id = cast(:x as uuid)"
        ),
        {
            "t": tenant,
            "x": execution,
            "f": group.first_event_at,
            "l": group.last_event_at,
            "d": group.duration_ms,
            "n": len(group.event_ids),
            "k": json.dumps(group.keys),
            "w": group.low_confidence,
            "s": execution_status(group, closed=False),
        },
    )


async def correlate_integration(
    engine: AsyncEngine, payload: Mapping[str, Any], correlator: Correlator | None = None
) -> int:
    """Correlaciona até PAGE pendentes da Integração; devolve quantos Eventos associou."""
    correlator = correlator or Correlator()
    integration = str(payload["integration_id"])
    async with engine.begin() as connection:
        await platform_role(connection)
        # A Organização sai da Integração, nunca da mensagem.
        tenant = await tenant_of(connection, integration)
        if tenant is None:
            return 0
        await connection.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"doctor.correlation:{integration}"},
        )
        pending = await load(connection, PENDING, t=tenant, i=integration, page=PAGE)
        if not pending:
            return 0
        known = await neighborhood(connection, tenant, integration, pending, correlator)
        events = {event.id: event for event in [*known, *pending]}
        waiting = {event.id: event for event in pending}
        for group in correlator.correlate(tenant, events.values()).groups:
            if not waiting.keys() & set(group.event_ids):
                continue
            refs = {r for e in group.event_ids if (r := events[e].execution_ref) is not None}
            execution = await resolve(connection, tenant, group, refs)
            await assign(connection, tenant, execution, group, waiting)
            await refresh(connection, tenant, execution, group)
        if len(pending) == PAGE:
            await connection.execute(
                text(
                    "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                    " values (cast(:t as uuid), 'correlation.requested', cast(:p as jsonb))"
                ),
                {"t": tenant, "p": json.dumps({"integration_id": integration})},
            )
        return len(pending)
