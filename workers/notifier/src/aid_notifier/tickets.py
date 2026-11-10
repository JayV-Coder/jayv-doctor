"""O que Jira e ServiceNow dividem no chamado (#43, #44): a reserva da tentativa, o contexto do
Incidente e do Diagnóstico que vai no corpo, e os desfechos que não dependem do provedor."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

CLAIM = timedelta(minutes=5)
NONE = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class Claimed:
    id: str
    tenant_id: str
    incident_id: str
    provider: str
    incident: Any
    diagnosis: Any
    recommendations: list[str]


async def claim(engine: AsyncEngine, ticket: str, provider: str | None = None) -> Claimed | None:
    """Reserva o chamado em `creating` por 5 min (duas entregas da mesma mensagem não criam ao
    mesmo tempo, e um worker que caiu no meio não o prende) e carrega o contexto do corpo."""
    async with engine.begin() as db:
        await platform_role(db)
        row = (
            await db.execute(
                text(
                    "update doctor.incident_tickets set claimed_at = now()"
                    " where id = cast(:t as uuid) and status = 'creating'"
                    " and (cast(:p as text) is null or provider = cast(:p as text))"
                    " and (claimed_at is null or claimed_at < now() - cast(:claim as interval))"
                    " returning id::text, tenant_id::text, incident_id::text, provider"
                ),
                {"t": ticket, "p": provider, "claim": CLAIM},
            )
        ).first()
        if row is None:
            return None
        incident = (
            await db.execute(
                text(
                    "select i.id::text, i.number, i.title, i.severity, i.category,"
                    " g.name as integration, g.environment from doctor.incidents i"
                    " join doctor.integrations g on g.tenant_id = i.tenant_id"
                    " and g.id = i.integration_id where i.id = cast(:i as uuid)"
                ),
                {"i": row.incident_id},
            )
        ).first()
        diagnosis = (
            await db.execute(
                text(
                    "select id::text, classification, probable_cause, confidence::float,"
                    " responsible_system from doctor.diagnoses"
                    " where incident_id = cast(:i as uuid)"
                    " and status in ('published', 'inconclusive', 'failed_llm')"
                    " order by version desc limit 1"
                ),
                {"i": row.incident_id},
            )
        ).first()
        recommendations = [
            str(found[0])
            for found in await db.execute(
                text(
                    "select text from doctor.diagnosis_recommendations"
                    " where diagnosis_id = cast(:d as uuid) order by rank"
                ),
                {"d": diagnosis.id if diagnosis else NONE},
            )
        ]
    return Claimed(
        row.id, row.tenant_id, row.incident_id, row.provider, incident, diagnosis, recommendations
    )


async def ticket_failed(engine: AsyncEngine, ticket: str, error: str) -> str:
    async with engine.begin() as db:
        await platform_role(db)
        await db.execute(
            text(
                "update doctor.incident_tickets set status = 'failed', error = :e"
                " where id = cast(:t as uuid) and status = 'creating'"
            ),
            {"e": error[:500], "t": ticket},
        )
    return "failed"


async def touch(engine: AsyncEngine, ticket: str) -> None:
    """Leitura que falhou vai para o fim da fila: um chamado que sempre falha (apagado no ITSM)
    não ocupa o lote de cada sincronização."""
    async with engine.begin() as db:
        await platform_role(db)
        await db.execute(
            text(
                "update doctor.incident_tickets set last_synced_at = now()"
                " where id = cast(:t as uuid)"
            ),
            {"t": ticket},
        )
