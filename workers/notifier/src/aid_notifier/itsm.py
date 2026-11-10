"""Chamados de ITSM: cada tópico vai para o provedor do chamado ou da conexão (#43, #44)."""

from collections.abc import Mapping
from typing import Any

import httpx
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_notifier import jira, servicenow


async def create_ticket(
    engine: AsyncEngine, ticket: str, transport: httpx.AsyncBaseTransport | None = None
) -> str:
    async with engine.begin() as db:
        await platform_role(db)
        provider = await db.scalar(
            text("select provider from doctor.incident_tickets where id = cast(:t as uuid)"),
            {"t": ticket},
        )
    if provider == "servicenow":
        return await servicenow.create_ticket(engine, ticket, transport)
    if provider == "jira":
        return await jira.create_ticket(engine, ticket, transport)
    return "skipped"


async def sync(
    engine: AsyncEngine,
    payload: Mapping[str, Any],
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
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
