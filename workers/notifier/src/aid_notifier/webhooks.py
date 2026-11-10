"""Entrega dos webhooks de saída (ticket #42).

`webhook.deliver` traz a primeira tentativa; a varredura (`POST /alerts/scan`) pega as que
venceram. Cada tentativa:

1. reserva a entrega (adia `next_attempt_at` 2 min: se o worker cair, outra tentativa vem);
2. monta o corpo `webhook.v1` na primeira vez (ids, títulos e links, nunca Eventos brutos) e o
   guarda para as próximas e para o "Reenviar";
3. assina com o segredo do Vault e envia pela rede que só conecta em endereço público;
4. 2xx encerra; o resto tenta de novo com espera exponencial (1, 2, 4… até 60 min) por até
   24 h. Com 50 falhas seguidas, o webhook desliga e os Admins recebem um e-mail.
"""

import json
import logging
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from aid_alerts import Message
from aid_alerts.network import UnsafeUrlError, check_url, public_transport, shape
from aid_alerts.signing import sign
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_notifier.channels import DeliveryError, Senders
from aid_notifier.notify import app_url

log = logging.getLogger(__name__)
WINDOW = timedelta(hours=24)
MAX_FAILURES = 50
BATCH = 50
EXCERPT = 1024
USER_AGENT = "IntegrationAIDoctor-Webhooks/1"


def backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(2 ** max(attempts - 1, 0), 60))


async def claim(connection: AsyncConnection, delivery: str) -> Any:
    return (
        await connection.execute(
            text(
                "update doctor.webhook_deliveries d set attempts = d.attempts + 1,"
                " next_attempt_at = now() + interval '2 minutes'"
                " from doctor.webhooks w where w.tenant_id = d.tenant_id and w.id = d.webhook_id"
                " and d.id = cast(:d as uuid) and d.status = 'pending'"
                " and d.next_attempt_at <= now()"
                " returning d.id::text, d.tenant_id::text, d.webhook_id::text, d.event,"
                " d.subject, d.body, d.attempts, d.created_at, w.url, w.enabled, w.name"
            ),
            {"d": delivery},
        )
    ).first()


async def incident_data(connection: AsyncConnection, incident: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                "select i.id::text, i.number, i.title, i.severity, i.status, i.category,"
                " g.id::text as integration_id, g.name as integration, g.environment"
                " from doctor.incidents i join doctor.integrations g"
                " on g.tenant_id = i.tenant_id and g.id = i.integration_id"
                " where i.id = cast(:i as uuid)"
            ),
            {"i": incident},
        )
    ).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "number": row.number,
        "title": row.title,
        "severity": row.severity,
        "status": row.status,
        "category": row.category,
        "environment": row.environment,
        "integration": {"id": row.integration_id, "name": row.integration},
        "url": f"{app_url()}/incidentes/{row.id}",
    }


async def build_body(connection: AsyncConnection, row: Any) -> dict[str, Any] | None:
    subject: Mapping[str, Any] = row.subject or {}
    data: dict[str, Any] = {}
    if subject.get("incident_id"):
        incident = await incident_data(connection, str(subject["incident_id"]))
        if incident is None:
            return None
        data["incident"] = incident
    if subject.get("diagnosis_id"):
        found = (
            await connection.execute(
                text(
                    "select d.id::text, d.incident_id::text, d.version, d.status,"
                    " d.classification, d.confidence::float, d.requires_human_review"
                    " from doctor.diagnoses d where d.id = cast(:d as uuid)"
                ),
                {"d": str(subject["diagnosis_id"])},
            )
        ).first()
        if found is None:
            return None
        data["diagnosis"] = {
            "id": found.id,
            "incident_id": found.incident_id,
            "version": found.version,
            "status": found.status,
            "classification": found.classification,
            # Confiança é sempre heurística (não calibrada).
            "confidence_heuristic": found.confidence,
            "requires_human_review": found.requires_human_review,
            "url": f"{app_url()}/incidentes/{found.incident_id}",
        }
    if subject.get("feedback_id"):
        verdict = await connection.scalar(
            text("select verdict from doctor.diagnosis_feedback where id = cast(:f as uuid)"),
            {"f": str(subject["feedback_id"])},
        )
        data["review"] = {"verdict": verdict}
    return {
        "version": "webhook.v1",
        "id": row.id,
        "event": row.event,
        "created_at": row.created_at.astimezone(UTC).isoformat(),
        "organization_id": row.tenant_id,
        "data": data,
    }


async def finish(
    engine: AsyncEngine,
    row: Any,
    *,
    ok: bool,
    status: int | None,
    latency_ms: int | None,
    excerpt: str | None,
    error: str | None,
    senders: Senders,
) -> str:
    """Grava o resultado e devolve o status final da entrega."""
    expired = datetime.now(UTC) - row.created_at >= WINDOW
    outcome = "succeeded" if ok else ("abandoned" if expired else "pending")
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "update doctor.webhook_deliveries set status = :o, response_status = :s,"
                " latency_ms = :l, response_excerpt = :x, error = :e,"
                " delivered_at = case when :ok then now() end,"
                " next_attempt_at = case when :o = 'pending' then now() + make_interval(secs => :b)"
                " end where id = cast(:d as uuid)"
            ),
            {
                "o": outcome,
                "s": status,
                "l": latency_ms,
                "x": excerpt[:EXCERPT] if excerpt else None,
                "e": error[:500] if error else None,
                "ok": ok,
                "b": backoff(row.attempts).total_seconds(),
                "d": row.id,
            },
        )
        failures = await connection.scalar(
            text(
                "update doctor.webhooks set last_status = :s, last_delivery_at = now(),"
                " failure_count = case when :ok then 0 else failure_count + 1 end"
                " where id = cast(:w as uuid) returning failure_count"
            ),
            {"s": status, "ok": ok, "w": row.webhook_id},
        )
        disable = not ok and failures is not None and failures >= MAX_FAILURES
        if disable:
            await connection.execute(
                text(
                    "update doctor.webhooks set enabled = false,"
                    " disabled_reason = '50 falhas seguidas' where id = cast(:w as uuid)"
                ),
                {"w": row.webhook_id},
            )
            await connection.execute(
                text(
                    "update doctor.webhook_deliveries set status = 'abandoned',"
                    " error = 'webhook desligado após 50 falhas seguidas'"
                    " where webhook_id = cast(:w as uuid) and status = 'pending'"
                ),
                {"w": row.webhook_id},
            )
            admins = [
                str(found[0])
                for found in await connection.execute(
                    text("select email from doctor.alert_audience(cast(:t as uuid), false)"),
                    {"t": row.tenant_id},
                )
                if found[0]
            ]
    if disable:
        try:
            await senders.email(
                admins,
                Message(
                    "Webhook desligado após 50 falhas seguidas",
                    f"O webhook {row.name} parou de receber eventos. Confira o endereço e"
                    " religue em Mais → Webhooks.",
                    f"{app_url()}/webhooks",
                    "Abrir os Webhooks",
                ),
            )
        except DeliveryError as exc:
            log.warning("aviso de webhook desligado não saiu: %s", exc)
        return "abandoned"
    return outcome


async def deliver(
    engine: AsyncEngine,
    delivery: str,
    senders: Senders,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Uma tentativa de entrega; devolve o status ('skipped' se não era a vez dela)."""
    async with engine.begin() as connection:
        await platform_role(connection)
        row = await claim(connection, delivery)
        if row is None:
            return "skipped"
        if not row.enabled:
            await connection.execute(
                text(
                    "update doctor.webhook_deliveries set status = 'abandoned',"
                    " error = 'webhook desligado' where id = cast(:d as uuid)"
                ),
                {"d": row.id},
            )
            return "abandoned"
        body = row.body
        if body is None:
            body = await build_body(connection, row)
            if body is None:
                await connection.execute(
                    text(
                        "update doctor.webhook_deliveries set status = 'abandoned',"
                        " error = 'o registro do evento não existe mais'"
                        " where id = cast(:d as uuid)"
                    ),
                    {"d": row.id},
                )
                return "abandoned"
            await connection.execute(
                text(
                    "update doctor.webhook_deliveries set body = cast(:b as jsonb)"
                    " where id = cast(:d as uuid)"
                ),
                {"b": json.dumps(body), "d": row.id},
            )
        secret = await connection.scalar(
            text("select doctor.get_webhook_secret(cast(:w as uuid))"), {"w": row.webhook_id}
        )
    content = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {
        "content-type": "application/json",
        "user-agent": USER_AGENT,
        "x-aid-event": row.event,
        "x-aid-delivery": row.id,
        "x-aid-signature": sign(str(secret), content),
    }
    started = time.monotonic()
    try:
        shape(row.url)
        if transport is None:
            await check_url(row.url)
        async with httpx.AsyncClient(
            transport=transport or public_transport(),
            timeout=httpx.Timeout(10.0),
            follow_redirects=False,
        ) as client:
            response = await client.post(row.url, content=content, headers=headers)
    except UnsafeUrlError as exc:
        return await finish(
            engine,
            row,
            ok=False,
            status=None,
            latency_ms=None,
            excerpt=None,
            error=f"endereço recusado: {exc}",
            senders=senders,
        )
    except httpx.HTTPError:
        return await finish(
            engine,
            row,
            ok=False,
            status=None,
            latency_ms=int((time.monotonic() - started) * 1000),
            excerpt=None,
            error="sem resposta (conexão, TLS ou tempo esgotado)",
            senders=senders,
        )
    latency = int((time.monotonic() - started) * 1000)
    ok = 200 <= response.status_code < 300
    return await finish(
        engine,
        row,
        ok=ok,
        status=response.status_code,
        latency_ms=latency,
        excerpt=response.text[:EXCERPT],
        error=None if ok else f"HTTP {response.status_code}",
        senders=senders,
    )


async def due(engine: AsyncEngine, senders: Senders) -> int:
    """Novas tentativas vencidas (varredura)."""
    async with engine.begin() as connection:
        await platform_role(connection)
        ids = [
            row[0]
            for row in await connection.execute(
                text(
                    "select id::text from doctor.webhook_deliveries where status = 'pending'"
                    " and next_attempt_at <= now() order by next_attempt_at limit :n"
                ),
                {"n": BATCH},
            )
        ]
    done = 0
    for delivery in ids:
        done += await deliver(engine, delivery, senders) == "succeeded"
    return done
