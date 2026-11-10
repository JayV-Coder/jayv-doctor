"""Chamados de ITSM: cada tópico vai para o provedor do chamado ou da conexão (#43, #44)."""

from collections.abc import Mapping
from typing import Any

import httpx
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_notifier import jira, servicenow
from aid_notifier.tickets import claim


async def create_ticket(
    engine: AsyncEngine, ticket: str, transport: httpx.AsyncBaseTransport | None = None
) -> str:
    # A reserva já diz o provedor: nada de consulta à parte.
    claimed = await claim(engine, ticket)
    if claimed is None:
        return "skipped"
    if claimed.provider == "servicenow":
        return await servicenow.open_incident(engine, claimed, transport)
    return await jira.open_issue(engine, claimed, transport)


async def sync(
    engine: AsyncEngine,
    payload: Mapping[str, Any],
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    provider = payload.get("provider")
    if provider is None:
        # Mensagens de antes do provedor no payload (configuração do Jira).
        async with engine.begin() as db:
            await platform_role(db)
            provider = await db.scalar(
                text("select provider from doctor.itsm_connections where id = cast(:c as uuid)"),
                {"c": str(payload["connection_id"])},
            )
    if provider == "servicenow":
        return await servicenow.sync(engine, payload, transport)
    if provider == "jira":
        return await jira.sync(engine, payload, transport)
    return 0


async def maintain(engine: AsyncEngine, transport: httpx.AsyncBaseTransport | None = None) -> int:
    return await jira.maintain(engine, transport) + await servicenow.maintain(engine, transport)
