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

import asyncio
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
TOTAL_SECONDS = 15
PARALLEL = 10


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


def with_link(snapshot: Mapping[str, Any], incident: str) -> dict[str, Any]:
    return {**snapshot, "url": f"{app_url()}/incidentes/{incident}"}


async def build_body(connection: AsyncConnection, row: Any) -> dict[str, Any] | None:
    """`webhook.v1` a partir do retrato gravado na hora do evento (o estado de agora poderia
    contradizer o evento); só os links são montados aqui."""
    subject: Mapping[str, Any] = row.subject or {}
    data: dict[str, Any] = {}
    incident = subject.get("incident")
    if isinstance(incident, Mapping):
        data["incident"] = with_link(incident, str(incident["id"]))
    diagnosis = subject.get("diagnosis")
    if isinstance(diagnosis, Mapping):
        data["diagnosis"] = with_link(diagnosis, str(diagnosis["incident_id"]))
    review = subject.get("review")
    if isinstance(review, Mapping):
        data["review"] = dict(review)
    if not data:
        return None
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
                # Só a entrega ainda em aberto: o desligamento do webhook já pode tê-la encerrado.
                " end where id = cast(:d as uuid) and status = 'pending'"
            ),
            {
                "o": outcome,
                "s": status,
                "l": latency_ms,
                "x": printable(excerpt) if excerpt else None,
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
        # Só quem desliga avisa: entregas em voo que falham depois não repetem o e-mail.
        disable = (
            not ok
            and failures is not None
            and failures >= MAX_FAILURES
            and await connection.scalar(
                text(
                    "update doctor.webhooks set enabled = false,"
                    " disabled_reason = '50 falhas seguidas'"
                    " where id = cast(:w as uuid) and enabled returning id"
                ),
                {"w": row.webhook_id},
            )
            is not None
        )
        if disable:
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


def printable(text_value: str) -> str:
    """O trecho da resposta como o Postgres aceita: sem NUL nem controles, até 1 KB."""
    return "".join(c for c in text_value if c.isprintable() or c in "\n\t")[:EXCERPT]


async def post(
    url: str, content: bytes, headers: dict[str, str], transport: httpx.AsyncBaseTransport | None
) -> tuple[int, str]:
    """(status, primeiro 1 KB da resposta), com prazo total de 15 s: um receptor que pinga um
    byte a cada 9 s ou devolve gigabytes não segura o worker."""
    async with asyncio.timeout(TOTAL_SECONDS):
        async with (
            httpx.AsyncClient(
                transport=transport or public_transport(),
                timeout=httpx.Timeout(10.0),
                follow_redirects=False,
            ) as client,
            client.stream("POST", url, content=content, headers=headers) as response,
        ):
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks += chunk
                if len(chunks) >= EXCERPT:
                    break
            return response.status_code, chunks[:EXCERPT].decode("utf-8", "replace")


async def prepare(engine: AsyncEngine, row: Any) -> tuple[dict[str, Any] | None, str | None]:
    """O corpo (montado na primeira tentativa e guardado) e o segredo; corpo nulo = o
    registro do evento sumiu."""
    async with engine.begin() as connection:
        await platform_role(connection)
        body = row.body
        if body is None:
            body = await build_body(connection, row)
            if body is None:
                return None, None
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
    return dict(body), str(secret)


async def abandon(engine: AsyncEngine, row: Any, reason: str) -> str:
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "update doctor.webhook_deliveries set status = 'abandoned', error = :e"
                " where id = cast(:d as uuid) and status = 'pending'"
            ),
            {"e": reason, "d": row.id},
        )
    return "abandoned"


async def deliver(
    engine: AsyncEngine,
    delivery: str,
    senders: Senders,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Uma tentativa de entrega; devolve o status ('skipped' se não era a vez dela). A reserva
    sai numa transação própria; qualquer falha depois dela conta como tentativa falha (com a
    janela de 24 h e a contagem de falhas), e nada fica `pending` para sempre."""
    async with engine.begin() as connection:
        await platform_role(connection)
        row = await claim(connection, delivery)
    if row is None:
        return "skipped"
    if not row.enabled:
        return await abandon(engine, row, "webhook desligado")
    started = time.monotonic()
    try:
        body, secret = await prepare(engine, row)
        if body is None or secret is None:
            return await abandon(engine, row, "o registro do evento não existe mais")
        content = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        headers = {
            "content-type": "application/json",
            "user-agent": USER_AGENT,
            "x-aid-event": row.event,
            "x-aid-delivery": row.id,
            "x-aid-signature": sign(secret, content),
        }
        shape(row.url)
        if transport is None:
            await check_url(row.url)
        started = time.monotonic()
        status, excerpt = await post(row.url, content, headers, transport)
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
    except (httpx.HTTPError, TimeoutError):
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
    except Exception:
        log.exception("tentativa de entrega %s falhou", row.id)
        return await finish(
            engine,
            row,
            ok=False,
            status=None,
            latency_ms=None,
            excerpt=None,
            error="falha interna na entrega",
            senders=senders,
        )
    ok = 200 <= status < 300
    return await finish(
        engine,
        row,
        ok=ok,
        status=status,
        latency_ms=int((time.monotonic() - started) * 1000),
        excerpt=excerpt,
        error=None if ok else f"HTTP {status}",
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
    # Até 10 ao mesmo tempo: 50 receptores lentos (15 s cada) cabem na rodada de 1 min.
    gate = asyncio.Semaphore(PARALLEL)

    async def one(delivery: str) -> bool:
        async with gate:
            return await deliver(engine, delivery, senders) == "succeeded"

    return sum(await asyncio.gather(*(one(delivery) for delivery in ids)))
