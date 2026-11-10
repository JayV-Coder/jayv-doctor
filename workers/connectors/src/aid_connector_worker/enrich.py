"""Consultas de enriquecimento (`enrichment.requested`, ticket #40). O worker de diagnóstico
grava as consultas pendentes de um Diagnóstico e o devolve à fila; aqui, o único worker que lê as
credenciais (ADR-0006) faz cada consulta de leitura pelo Conector do Mapa, grava o resultado e
pede o Diagnóstico de novo. Consulta que falha vira `failed` com a mensagem classificada do
Conector (nunca a resposta do destino), e o Diagnóstico segue sem ela."""

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import Any

from aid_connectors.base import Connector, ConnectorError, LookupQuery, LookupResult, Secret
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_connector_worker.sync import secret_of

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 30

PENDING = text(
    "select en.id::text, en.tenant_id::text, en.reference, en.entity, en.field,"
    " m.lookup ->> 'status_field' as status_field, c.id::text as connector_id, c.provider,"
    " c.config, c.status as connector_status"
    " from doctor.enrichments en"
    " left join doctor.correlation_mappings m"
    " on m.tenant_id = en.tenant_id and m.id = en.mapping_id"
    " left join doctor.connectors c on c.tenant_id = en.tenant_id and c.id = en.connector_id"
    " where en.diagnosis_id = cast(:d as uuid) and en.outcome = 'pending' order by en.created_at"
)


async def finish(
    engine: AsyncEngine, row: Any, result: LookupResult | None, error: str | None
) -> None:
    outcome = "failed" if result is None else ("found" if result.found else "not_found")
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "update doctor.enrichments set outcome = :o, record_id = :r, record_status = :s,"
                " error = :e, checked_at = now()"
                " where tenant_id = cast(:t as uuid) and id = cast(:id as uuid)"
                " and outcome = 'pending'"
            ),
            {
                "o": outcome,
                "r": result.record_id[:256] if result and result.record_id else None,
                "s": result.status[:128] if result and result.status else None,
                "e": error[:500] if error else None,
                "t": row.tenant_id,
                "id": row.id,
            },
        )


async def consult(
    engine: AsyncEngine, row: Any, registry: Mapping[str, type[Connector]]
) -> tuple[LookupResult | None, str | None]:
    if row.connector_id is None:
        return None, "O Conector da consulta foi removido."
    if row.connector_status == "disabled":
        return None, "O Conector da consulta está desativado."
    kind = registry.get(row.provider)
    instance: Any = kind() if kind is not None else None
    if instance is None or not hasattr(instance, "lookup"):
        return None, "Este Conector não faz consultas."
    secret = Secret(await secret_of(engine, row.connector_id))
    query = LookupQuery(row.entity, row.field, row.reference, row.status_field)
    try:
        result: LookupResult = await asyncio.wait_for(
            instance.lookup(secret, row.config or {}, query), TIMEOUT_SECONDS
        )
    except ConnectorError as exc:
        return None, exc.message
    except TimeoutError:
        return None, f"O sistema não respondeu à consulta em {TIMEOUT_SECONDS} s."
    return result, None


async def run_enrichment(
    engine: AsyncEngine, payload: Mapping[str, Any], registry: Mapping[str, type[Connector]]
) -> int:
    """Faz as consultas pendentes do Diagnóstico e o pede de novo; devolve quantas fez."""
    diagnosis = str(payload["diagnosis_id"])
    async with engine.begin() as connection:
        await platform_role(connection)
        rows = list(await connection.execute(PENDING, {"d": diagnosis}))
    for row in rows:
        try:
            result, error = await consult(engine, row, registry)
        except Exception:
            # Falha inesperada numa consulta não segura o Diagnóstico: vira `failed`.
            log.exception("consulta de enriquecimento %s falhou", row.id)
            result, error = None, "Falha interna na consulta."
        await finish(engine, row, result, error)
    if rows:
        async with engine.begin() as connection:
            await platform_role(connection)
            await connection.execute(
                text(
                    "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                    " values (cast(:t as uuid), 'diagnosis.requested', cast(:p as jsonb))"
                ),
                {"t": rows[0].tenant_id, "p": json.dumps({"diagnosis_id": diagnosis})},
            )
    return len(rows)
