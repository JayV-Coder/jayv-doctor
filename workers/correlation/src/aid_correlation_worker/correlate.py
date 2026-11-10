"""Correlação dos Eventos pendentes de uma Integração (`correlation.requested`).

Cada mensagem só diz qual Integração tem Eventos novos; o worker pega os pendentes
(`execution_ref` nulo), a vizinhança já correlacionada que pode se ligar a eles (mesmos ids,
Referência na janela de cada pendente, mesmo recurso na proximidade) e os demais Eventos dessas
Execuções, e roda o motor sobre o conjunto. Execuções nunca se dividem nem são apagadas: a que se
revela igual a outra é marcada `merged_into` a mais antiga, com histórico em `execution_merges`
(ADR-0012). Um lock por Integração serializa as mensagens concorrentes; a mensagem repetida não
acha pendentes e termina sem efeito. As escritas vão em lote: poucas idas ao banco por mensagem.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from aid_correlation import (
    Correlator,
    EventRef,
    Group,
    IdentifierMap,
    MappingError,
    cross_keys,
    execution_status,
    merge_plan,
    parse_keys,
)
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
    " e.execution_ref::text as execution_ref, coalesce(e.cross_keys, '{}') as cross_keys"
)

# Os pendentes trazem também o que o Mapa de identificadores lê (#40); as chaves calculadas são
# gravadas junto com a Execução, e os já correlacionados usam a coluna `cross_keys`.
PENDING = text(
    f"select {COLUMNS}, e.source, e.attributes, e.error from doctor.events e"  # noqa: S608
    " where e.tenant_id = cast(:t as uuid) and e.integration_id = cast(:i as uuid)"
    " and e.execution_ref is null order by e.timestamp, e.id limit :page"
)

# A janela da Referência e a da proximidade são por pendente (unnest), não o intervalo da página
# inteira: uma Importação de 7 dias não puxa a semana toda.
NEIGHBORS = text(
    f"select {COLUMNS} from doctor.events e"  # noqa: S608
    " where e.tenant_id = cast(:t as uuid) and e.integration_id = cast(:i as uuid)"
    " and e.execution_ref is not null and ("
    "  e.execution_id = any(cast(:execs as text[])) or e.trace_id = any(cast(:traces as text[]))"
    "  or exists (select 1 from unnest(cast(:refs as text[]), cast(:ref_at as timestamptz[]))"
    "   as p(ref, at) where e.business_reference = p.ref"
    "   and e.timestamp between p.at - make_interval(secs => :window)"
    "   and p.at + make_interval(secs => :window))"
    "  or exists (select 1 from unnest(cast(:resources as text[]),"
    "   cast(:resource_at as timestamptz[])) as p(resource, at)"
    "   where e.source ->> 'resource' = p.resource"
    "   and e.timestamp between p.at - make_interval(secs => :near)"
    "   and p.at + make_interval(secs => :near))"
    "  or (e.cross_keys && cast(:links as text[]) and e.timestamp between :lo and :hi))"
)

MAPS = text(
    "select id::text, keys, window_minutes from doctor.correlation_mappings"
    " where tenant_id = cast(:t as uuid) and integration_id = cast(:i as uuid) order by id"
)

MEMBERS = text(
    f"select {COLUMNS} from doctor.events e"  # noqa: S608
    " where e.tenant_id = cast(:t as uuid) and e.execution_ref = any(cast(:refs as uuid[]))"
)


@dataclass(frozen=True)
class Existing:
    id: str
    first_event_at: datetime
    correlation_keys: Mapping[str, Any]
    low_confidence: bool


EXTRA = ("source", "attributes", "error")


def to_ref(row: Row[Any], maps: Sequence[IdentifierMap] = ()) -> EventRef:
    fields = row._asdict()
    contract = {name: fields.pop(name) for name in EXTRA if name in fields}
    stored = tuple(fields.pop("cross_keys") or ())
    if contract:
        keys = cross_keys({**fields, **contract}, maps)
    else:
        # Chave gravada de um Mapa que já foi removido não une mais nada: mudar ou remover um
        # Mapa vale para o que vem depois, como a tela promete.
        current = {item.id for item in maps}
        keys = tuple(key for key in stored if key.split(":", 1)[0] in current)
    return EventRef(**fields, cross_keys=keys)


async def identifier_maps(
    connection: AsyncConnection, tenant: str, integration: str
) -> list[IdentifierMap]:
    found = []
    for row in await connection.execute(MAPS, {"t": tenant, "i": integration}):
        try:
            keys = parse_keys(row.keys)
        except MappingError:
            # Gravado pela API já validado; um mapa que deixou de valer não derruba a correlação.
            continue
        found.append(IdentifierMap(row.id, keys, timedelta(minutes=row.window_minutes)))
    return found


async def load(
    connection: AsyncConnection,
    query: Any,
    maps: Sequence[IdentifierMap] = (),
    **params: Any,
) -> list[EventRef]:
    return [to_ref(row, maps) for row in await connection.execute(query, params)]


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
    maps: Sequence[IdentifierMap] = (),
) -> list[EventRef]:
    def values(name: str) -> list[str]:
        return sorted({str(getattr(e, name)) for e in pending if getattr(e, name) is not None})

    links = sorted({key for e in pending for key in e.cross_keys})
    widest = max((correlator.settings.window_of(key) for key in links), default=timedelta(0))
    with_reference = [e for e in pending if e.business_reference is not None]
    with_resource = [e for e in pending if e.resource is not None and e.attempt is not None]
    neighbors = await load(
        connection,
        NEIGHBORS,
        maps,
        t=tenant,
        i=integration,
        execs=values("execution_id"),
        traces=values("trace_id"),
        refs=[e.business_reference for e in with_reference],
        ref_at=[e.timestamp for e in with_reference],
        resources=[e.resource for e in with_resource],
        resource_at=[e.timestamp for e in with_resource],
        window=correlator.settings.reference_window.total_seconds(),
        near=correlator.settings.proximity.total_seconds(),
        links=links,
        lo=min(e.timestamp for e in pending) - widest,
        hi=max(e.timestamp for e in pending) + widest,
    )
    refs = sorted({e.execution_ref for e in neighbors if e.execution_ref})
    members = await load(connection, MEMBERS, maps, t=tenant, refs=refs) if refs else []
    return [*neighbors, *members]


async def existing(connection: AsyncConnection, tenant: str, refs: set[str]) -> dict[str, Existing]:
    if not refs:
        return {}
    rows = await connection.execute(
        text(
            "select id::text, first_event_at, correlation_keys, low_confidence"
            " from doctor.executions"
            " where tenant_id = cast(:t as uuid) and id = any(cast(:ids as uuid[]))"
            " order by id for update"
        ),
        {"t": tenant, "ids": sorted(refs)},
    )
    return {row.id: Existing(*row) for row in rows}


async def merge(connection: AsyncConnection, tenant: str, survivor: str, found: Existing) -> None:
    """Marca a Execução como fundida, leva os Eventos (e as já fundidas nela) para a
    sobrevivente e guarda o histórico. Nada é apagado: quem apontava para ela continua achando."""
    params = {"t": tenant, "s": survivor, "m": found.id}
    await connection.execute(
        text(
            "insert into doctor.execution_merges"
            " (tenant_id, survivor_id, merged_id, merged_keys)"
            " values (cast(:t as uuid), cast(:s as uuid), cast(:m as uuid), cast(:k as jsonb))"
        ),
        {**params, "k": json.dumps(dict(found.correlation_keys))},
    )
    await connection.execute(
        text(
            "update doctor.events set execution_ref = cast(:s as uuid)"
            " where tenant_id = cast(:t as uuid) and execution_ref = cast(:m as uuid)"
        ),
        params,
    )
    await connection.execute(
        text(
            "update doctor.executions set merged_into = cast(:s as uuid),"
            " event_count = case when id = cast(:m as uuid) then 0 else event_count end,"
            " closed_at = coalesce(closed_at, now())"
            " where tenant_id = cast(:t as uuid)"
            " and (id = cast(:m as uuid) or merged_into = cast(:m as uuid))"
        ),
        params,
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
        maps = await identifier_maps(connection, tenant, integration)
        if maps:
            windows = {item.id: item.window for item in maps}
            correlator = Correlator(replace(correlator.settings, cross_windows=windows))
        pending = await load(connection, PENDING, maps, t=tenant, i=integration, page=PAGE)
        if not pending:
            return 0
        known = await neighborhood(connection, tenant, integration, pending, correlator, maps)
        events = {event.id: event for event in [*known, *pending]}
        waiting = {event.id: event for event in pending}
        groups = [
            group
            for group in correlator.correlate(tenant, events.values()).groups
            if waiting.keys() & set(group.event_ids)
        ]
        found = await existing(
            connection, tenant, {e.execution_ref for e in known if e.execution_ref is not None}
        )

        targets: list[tuple[Group, str, bool]] = []
        created: list[dict[str, Any]] = []
        for group in groups:
            mine = {
                ref
                for event_id in group.event_ids
                if (ref := events[event_id].execution_ref) is not None and ref in found
            }
            survivor, merged = merge_plan({ref: found[ref].first_event_at for ref in mine})
            if survivor is None:
                survivor = str(uuid4())
                created.append(
                    {
                        "id": survivor,
                        "t": tenant,
                        "i": integration,
                        "f": group.first_event_at,
                        "l": group.last_event_at,
                    }
                )
            for target in merged:
                await merge(connection, tenant, survivor, found[target])
            was_weak = any(found[ref].low_confidence for ref in mine)
            targets.append((group, survivor, was_weak))

        if created:
            await connection.execute(
                text(
                    "insert into doctor.executions (id, tenant_id, integration_id,"
                    " first_event_at, last_event_at) values (cast(:id as uuid),"
                    " cast(:t as uuid), cast(:i as uuid), :f, :l)"
                ),
                created,
            )
        # Com o instante na condição: o Postgres vai direto à partição do Evento.
        await connection.execute(
            text(
                "update doctor.events set execution_ref = cast(:x as uuid), correlated_by = :c,"
                " cross_keys = nullif(cast(:k as text[]), '{}')"
                " where tenant_id = cast(:t as uuid) and id = cast(:id as uuid)"
                " and timestamp = :ts"
            ),
            [
                {
                    "t": tenant,
                    "id": event_id,
                    "ts": waiting[event_id].timestamp,
                    "x": execution,
                    "c": group.correlated_by.get(event_id),
                    "k": list(waiting[event_id].cross_keys),
                }
                for group, execution, _ in targets
                for event_id in group.event_ids
                if event_id in waiting
            ],
        )
        # Os números saem do grupo inteiro; Evento novo reabre a Execução (fecha de novo em 5 min).
        await connection.execute(
            text(
                "update doctor.executions set first_event_at = :f, last_event_at = :l,"
                " duration_ms = :d, event_count = :n, correlation_keys = cast(:k as jsonb),"
                " low_confidence = :w, status = :s, last_activity_at = now(), closed_at = null,"
                " reconciled_at = null"
                " where tenant_id = cast(:t as uuid) and id = cast(:x as uuid)"
            ),
            [
                {
                    "t": tenant,
                    "x": execution,
                    "f": group.first_event_at,
                    "l": group.last_event_at,
                    "d": group.duration_ms,
                    "n": len(group.event_ids),
                    "k": json.dumps(group.keys),
                    "w": group.low_confidence or was_weak,
                    "s": execution_status(group, closed=False),
                }
                for group, execution, was_weak in targets
            ],
        )
        if len(pending) == PAGE:
            await connection.execute(
                text(
                    "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                    " values (cast(:t as uuid), 'correlation.requested', cast(:p as jsonb))"
                ),
                {"t": tenant, "p": json.dumps({"integration_id": integration})},
            )
        return len(pending)
