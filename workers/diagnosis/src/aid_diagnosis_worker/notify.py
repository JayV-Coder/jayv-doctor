"""Avisos de Cota (ticket #31): aos 80% e aos 100% de um recurso, e-mail para Owner e Admin da
Organização (o push chega na v0.3). A mensagem `usage.threshold` sai uma vez por patamar e
período (`usage_alerts`). SMTP como o da API (`aid_api.orgs.mailer`): `smtp://` com STARTTLS
quando há usuário, `smtps://` direto."""

import asyncio
from collections.abc import Mapping
from typing import Any

from aid_alerts.mail import FROM_ADDRESS, Mailer, SmtpMailer, mailer_from_env
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

RESOURCES = {
    "events_ingested": "Eventos ingeridos no mês",
    "diagnoses_llm": "Diagnósticos com IA no mês",
    "storage_bytes": "Armazenamento",
}


# O envio SMTP é o mesmo dos alertas (#41).
__all__ = ["FROM_ADDRESS", "Mailer", "SmtpMailer", "mailer_from_env"]


def message(resource: str, threshold: int, organization: str) -> tuple[str, str]:
    label = RESOURCES.get(resource, resource)
    if threshold >= 100:
        subject = f"{organization}: Cota de {label.lower()} atingida"
        effect = (
            "Novos Diagnósticos rodam só com as Regras até o próximo mês."
            if resource == "diagnoses_llm"
            else "A ingestão é recusada acima da tolerância do plano."
            if resource == "events_ingested"
            else "Veja o uso no menu Mais, em Uso e cotas."
        )
    else:
        subject = f"{organization}: {threshold}% da Cota de {label.lower()}"
        effect = "Veja o uso no menu Mais, em Uso e cotas."
    body = (
        f"A organização {organization} chegou a {threshold}% da Cota de {label.lower()}.\n\n"
        f"{effect}\n\nPara ampliar o plano, fale com a equipe do Integration AI Doctor.\n"
    )
    return subject, body


async def notify_threshold(engine: AsyncEngine, payload: Mapping[str, Any], mailer: Mailer) -> int:
    tenant = str(payload["tenant_id"])
    async with engine.begin() as connection:
        await platform_role(connection)
        rows = (
            await connection.execute(
                text("select organization, email from doctor.quota_recipients(cast(:t as uuid))"),
                {"t": tenant},
            )
        ).all()
    emails = [row.email for row in rows]
    organization = rows[0].organization if rows else None
    if not emails:
        return 0
    subject, body = message(
        str(payload["resource"]), int(payload["threshold"]), organization or "sua organização"
    )
    # smtplib é bloqueante: fora do laço de eventos.
    await asyncio.to_thread(mailer.send, emails, subject, body)
    return len(emails)
