"""Avaliação das Regras de alerta e entrega (ticket #41, ADR-0017).

`alert.evaluate` chega da outbox (Incidente aberto ou atualizado, Diagnóstico publicado, Conector
em `failing`); a varredura agendada (`POST /alerts/scan`) cobre taxa de erro e Diagnóstico
aguardando revisão. Para cada Regra que casa:

1. deduplicação: um lock por (Regra, assunto) e no máximo uma notificação a cada 15 min (o
   Diagnóstico aguardando revisão notifica uma vez só). 37 Execuções no mesmo Incidente geram uma;
2. silêncio da Regra e de cada Usuário fora do plantão, exceto Incidente crítico;
3. entrega em cada canal da Regra, com o resultado em `notification_deliveries`.
"""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from aid_alerts import (
    AlertError,
    Conditions,
    IncidentFacts,
    Message,
    in_quiet_hours,
    incident_matches,
    message_for_incident,
    parse_conditions,
    parse_quiet_hours,
)
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_notifier.channels import DeliveryError, PushTarget, Senders

log = logging.getLogger(__name__)
REPEAT = timedelta(minutes=15)
HISTORY_DAYS = 30


def app_url() -> str:
    return os.environ.get("APP_URL", "http://127.0.0.1:3000").rstrip("/")


@dataclass(frozen=True)
class Rule:
    id: str
    tenant_id: str
    conditions: Conditions
    channels: tuple[str, ...]
    quiet: Any


@dataclass(frozen=True)
class Notice:
    """O que notificar: assunto (base da deduplicação), mensagem e se fura o silêncio."""

    subject: str
    message: Message
    critical: bool = False
    once: bool = False


async def rules_of(connection: AsyncConnection, tenant: str, kind: str) -> list[Rule]:
    rows = await connection.execute(
        text(
            "select id::text, tenant_id::text, conditions, channels, quiet_hours"
            " from doctor.alert_rules where tenant_id = cast(:t as uuid) and enabled"
            " and conditions ->> 'type' = :k order by id"
        ),
        {"t": tenant, "k": kind},
    )
    found = []
    for row in rows:
        try:
            conditions = parse_conditions(row.conditions)
            quiet = parse_quiet_hours(row.quiet_hours)
        except AlertError:
            # Gravada pela API já validada; uma Regra que deixou de valer não derruba as outras.
            log.warning("Regra de alerta %s inválida, ignorada", row.id)
            continue
        found.append(
            Rule(row.id, row.tenant_id, conditions, tuple(str(c) for c in row.channels), quiet)
        )
    return found


async def lock(connection: AsyncConnection, rule: Rule, notice: Notice) -> None:
    """Lock por assunto na Organização: entregas concorrentes do mesmo Incidente (e Regras que
    se sobrepõem) passam uma de cada vez pela reserva."""
    await connection.execute(
        text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"doctor.alert:{rule.tenant_id}:{notice.subject}"},
    )


async def busy(connection: AsyncConnection, rule: Rule, notice: Notice, channel: str) -> bool:
    """O canal já recebeu (ou está recebendo) este assunto: enviado há menos de 15 min,
    reservado há menos de 2 min (o worker pode ter caído no meio) ou falhou há menos de 5 min
    (espera antes de tentar de novo um canal quebrado). Por canal, não por Regra: duas Regras no
    mesmo canal não duplicam."""
    found = await connection.scalar(
        text(
            "select 1 from doctor.notification_deliveries where tenant_id = cast(:t as uuid)"
            " and subject = :s and channel_id = cast(:c as uuid) and ("
            " (status = 'sent' and (:once or created_at > now() - make_interval(secs => :w)))"
            " or (status = 'pending' and created_at > now() - interval '2 minutes')"
            " or (status = 'failed' and created_at > now() - interval '5 minutes')) limit 1"
        ),
        {
            "t": rule.tenant_id,
            "s": notice.subject,
            "c": channel,
            "once": notice.once,
            "w": REPEAT.total_seconds(),
        },
    )
    return found is not None


async def record(
    connection: AsyncConnection,
    rule: Rule,
    notice: Notice,
    channel: str | None,
    status: str,
    error: str | None = None,
) -> str:
    return str(
        await connection.scalar(
            text(
                "insert into doctor.notification_deliveries (tenant_id, rule_id, channel_id,"
                " subject, status, error) values (cast(:t as uuid), cast(:r as uuid),"
                " cast(:c as uuid), :s, :st, :e) returning id::text"
            ),
            {
                "t": rule.tenant_id,
                "r": rule.id,
                "c": channel,
                "s": notice.subject,
                "st": status,
                "e": error[:500] if error else None,
            },
        )
    )


async def audience(
    connection: AsyncConnection, tenant: str, scope: str, critical: bool, now: datetime
) -> list[tuple[str, str]]:
    """(user_id, e-mail) dos Usuários da Organização no público do canal, fora do silêncio de
    cada um (o crítico chega mesmo assim)."""
    rows = await connection.execute(
        text(
            "select user_id::text, email, quiet_hours"
            " from doctor.alert_audience(cast(:t as uuid), :all)"
        ),
        {"t": tenant, "all": scope == "all"},
    )
    found = []
    for row in rows:
        try:
            quiet = parse_quiet_hours(row.quiet_hours)
        except AlertError:
            quiet = None
        if critical or not in_quiet_hours(quiet, now):
            found.append((row.user_id, row.email or ""))
    return found


async def deliver_channel(
    engine: AsyncEngine,
    rule: Rule,
    notice: Notice,
    channel: Any,
    senders: Senders,
    now: datetime,
) -> tuple[str, str | None]:
    """(status, erro) da entrega num canal."""
    try:
        if channel.type in ("jira", "servicenow"):
            # Canal de ITSM: abre o chamado do Incidente (uma vez só, pela reserva única).
            if not notice.subject.startswith("incident:"):
                return "quiet", "o canal de ITSM só abre chamado de Incidente"
            incident = notice.subject.split(":")[1]
            async with engine.begin() as connection:
                await platform_role(connection)
                await connection.execute(
                    text(
                        "select doctor.queue_ticket(cast(:t as uuid), cast(:i as uuid), null,"
                        " cast(:r as uuid), :p)"
                    ),
                    {"t": rule.tenant_id, "i": incident, "r": rule.id, "p": channel.type},
                )
            return "sent", None
        if channel.type in ("slack", "teams"):
            async with engine.begin() as connection:
                await platform_role(connection)
                url = await connection.scalar(
                    text("select doctor.get_channel_secret(cast(:c as uuid))"), {"c": channel.id}
                )
            await senders.webhook(channel.type, str(url), notice.message)
            return "sent", None
        scope = str((channel.config or {}).get("audience", "managers"))
        async with engine.begin() as connection:
            await platform_role(connection)
            people = await audience(connection, rule.tenant_id, scope, notice.critical, now)
            targets = [
                PushTarget(*row)
                for row in await connection.execute(
                    text(
                        "select id::text, endpoint, p256dh, auth from doctor.push_subscriptions"
                        " where tenant_id = cast(:t as uuid)"
                        " and user_id = any(cast(:u as uuid[]))"
                    ),
                    {"t": rule.tenant_id, "u": [user for user, _ in people]},
                )
            ]
        # Os envios ficam fora da transação: um SMTP lento não segura conexão do Supavisor.
        if channel.type == "email":
            emails = sorted({email for _, email in people if email})
            if not emails:
                return "quiet", "ninguém fora do silêncio"
            await senders.email(emails, notice.message)
            return "sent", None
        if not targets:
            return "quiet", "nenhum aparelho com push fora do silêncio"
        delivered, gone = 0, []
        for target in targets:
            try:
                if await senders.push(target, notice.message):
                    delivered += 1
                else:
                    gone.append(target.id)
            except DeliveryError as exc:
                log.warning("push falhou para uma assinatura: %s", exc)
        async with engine.begin() as connection:
            await platform_role(connection)
            if gone:
                await connection.execute(
                    text(
                        "delete from doctor.push_subscriptions where id = any(cast(:i as uuid[]))"
                    ),
                    {"i": gone},
                )
        return ("sent", None) if delivered else ("failed", "nenhum aparelho aceitou o push")
    except DeliveryError as exc:
        return "failed", str(exc)
    except Exception:
        # Qualquer outra falha (segredo sumido, banco) vira `failed` deste canal; os outros
        # canais seguem.
        log.exception("entrega no canal %s falhou", channel.id)
        return "failed", "falha interna na entrega"


async def notify(
    engine: AsyncEngine, rule: Rule, notice: Notice, senders: Senders, now: datetime
) -> int:
    """Entrega uma notificação da Regra; devolve quantos canais a receberam."""
    chosen: list[tuple[Any, str]] = []
    async with engine.begin() as connection:
        await platform_role(connection)
        await lock(connection, rule, notice)
        if not notice.critical and in_quiet_hours(rule.quiet, now):
            await record(connection, rule, notice, None, "quiet")
            return 0
        channels = list(
            await connection.execute(
                text(
                    "select id::text, type, config from doctor.notification_channels"
                    " where tenant_id = cast(:t as uuid) and id = any(cast(:c as uuid[]))"
                ),
                {"t": rule.tenant_id, "c": list(rule.channels)},
            )
        )
        # A reserva (`pending`) sai antes do envio: outra mensagem do mesmo assunto, que espera
        # este lock, já a vê e não duplica.
        for channel in channels:
            if await busy(connection, rule, notice, channel.id):
                await record(connection, rule, notice, channel.id, "suppressed")
            else:
                chosen.append(
                    (channel, await record(connection, rule, notice, channel.id, "pending"))
                )
    sent = 0
    for channel, delivery in chosen:
        status, error = await deliver_channel(engine, rule, notice, channel, senders, now)
        sent += status == "sent"
        async with engine.begin() as connection:
            await platform_role(connection)
            await connection.execute(
                text(
                    "update doctor.notification_deliveries set status = :s, error = :e"
                    " where id = cast(:d as uuid)"
                ),
                {"s": status, "e": error[:500] if error else None, "d": delivery},
            )
    return sent


async def incident_facts(connection: AsyncConnection, incident: str) -> IncidentFacts | None:
    row = (
        await connection.execute(
            text(
                "select i.id::text, i.number, i.title, i.severity, g.environment,"
                " g.id::text as integration_id, g.name from doctor.incidents i"
                " join doctor.integrations g on g.tenant_id = i.tenant_id"
                " and g.id = i.integration_id where i.id = cast(:i as uuid)"
                " and i.status in ('open', 'investigating')"
            ),
            {"i": incident},
        )
    ).first()
    return IncidentFacts(*row) if row is not None else None


async def evaluate(
    engine: AsyncEngine, payload: Mapping[str, Any], senders: Senders, now: datetime | None = None
) -> int:
    """`alert.evaluate`: devolve quantas notificações saíram."""
    now = now or datetime.now(UTC)
    source = str(payload.get("source", ""))
    notices: list[tuple[Rule, Notice]] = []
    async with engine.begin() as connection:
        await platform_role(connection)
        if source in ("incident.opened", "incident.updated") and payload.get("incident_id"):
            facts = await incident_facts(connection, str(payload["incident_id"]))
            if facts is None:
                return 0
            tenant = await connection.scalar(
                text("select tenant_id::text from doctor.incidents where id = cast(:i as uuid)"),
                {"i": facts.id},
            )
            event = "opened" if source == "incident.opened" else "updated"
            for rule in await rules_of(connection, str(tenant), "incident"):
                if incident_matches(rule.conditions, facts, event):
                    notices.append(
                        (
                            rule,
                            # A severidade no assunto: escalar para crítico notifica de novo.
                            Notice(
                                f"incident:{facts.id}:{facts.severity}",
                                message_for_incident(facts, app_url(), event),
                                critical=facts.severity == "critical",
                            ),
                        )
                    )
        elif source == "connector.failing" and payload.get("connector_id"):
            row = (
                await connection.execute(
                    text(
                        "select c.id::text, c.tenant_id::text, c.name, c.integration_id::text,"
                        " g.name as integration from doctor.connectors c"
                        " join doctor.integrations g on g.tenant_id = c.tenant_id"
                        " and g.id = c.integration_id"
                        " where c.id = cast(:c as uuid) and c.status = 'failing'"
                    ),
                    {"c": str(payload["connector_id"])},
                )
            ).first()
            if row is None:
                return 0
            for rule in await rules_of(connection, row.tenant_id, "connector_failing"):
                scope = rule.conditions.integrations
                if scope and row.integration_id not in scope:
                    continue
                notices.append(
                    (
                        rule,
                        Notice(
                            f"connector:{row.id}",
                            Message(
                                "Conector com falhas",
                                f"{row.name} · {row.integration}"[:300],
                                f"{app_url()}/conectores",
                                "Abrir os Conectores",
                            ),
                        ),
                    )
                )
    sent = 0
    for rule, notice in notices:
        sent += await notify(engine, rule, notice, senders, now)
    return sent


async def scan(engine: AsyncEngine, senders: Senders, now: datetime | None = None) -> int:
    """Varredura agendada: taxa de erro por Integração e Diagnóstico aguardando revisão."""
    now = now or datetime.now(UTC)
    notices: list[tuple[Rule, Notice]] = []
    async with engine.begin() as connection:
        await platform_role(connection)
        # O histórico de entregas guarda 30 dias; cada varredura apaga um lote do que passou.
        await connection.execute(
            text(
                "delete from doctor.notification_deliveries where id in ("
                " select id from doctor.notification_deliveries"
                " where created_at < now() - make_interval(days => :d) limit 1000)"
            ),
            {"d": HISTORY_DAYS},
        )
        tenants = [
            row[0]
            for row in await connection.execute(
                text(
                    "select distinct tenant_id::text from doctor.alert_rules where enabled"
                    " and conditions ->> 'type' in ('error_rate', 'diagnosis_review')"
                )
            )
        ]
        for tenant in tenants:
            for rule in await rules_of(connection, tenant, "error_rate"):
                notices += await error_rate(connection, rule)
            for rule in await rules_of(connection, tenant, "diagnosis_review"):
                notices += await awaiting_review(connection, rule)
    sent = 0
    for rule, notice in notices:
        sent += await notify(engine, rule, notice, senders, now)
    return sent


async def error_rate(connection: AsyncConnection, rule: Rule) -> list[tuple[Rule, Notice]]:
    found = await connection.execute(
        text(
            "select g.id::text, g.name, count(*) as total,"
            " count(*) filter (where x.status = 'failed') as failed"
            " from doctor.executions x join doctor.integrations g"
            " on g.tenant_id = x.tenant_id and g.id = x.integration_id"
            " where x.tenant_id = cast(:t as uuid) and x.merged_into is null"
            " and x.first_event_at > now() - make_interval(mins => :m)"
            " and (cardinality(cast(:i as uuid[])) = 0 or g.id = any(cast(:i as uuid[])))"
            " group by g.id, g.name"
        ),
        {
            "t": rule.tenant_id,
            "m": rule.conditions.minutes,
            "i": list(rule.conditions.integrations),
        },
    )
    notices = []
    for row in found:
        if row.total < rule.conditions.min_executions:
            continue
        pct = 100 * row.failed / row.total
        if pct <= rule.conditions.threshold_pct:
            continue
        notices.append(
            (
                rule,
                Notice(
                    f"error_rate:{row.id}",
                    Message(
                        f"Taxa de erro acima de {rule.conditions.threshold_pct:g}%",
                        f"{row.name} · {pct:.0f}% em {rule.conditions.minutes} min",
                        f"{app_url()}/execucoes",
                        "Abrir as Execuções",
                    ),
                ),
            )
        )
    return notices


async def awaiting_review(connection: AsyncConnection, rule: Rule) -> list[tuple[Rule, Notice]]:
    found = await connection.execute(
        text(
            "select d.id::text, i.id::text as incident, i.title, g.name"
            " from doctor.diagnoses d join doctor.incidents i"
            " on i.tenant_id = d.tenant_id and i.id = d.incident_id"
            " join doctor.integrations g on g.tenant_id = i.tenant_id and g.id = i.integration_id"
            " where d.tenant_id = cast(:t as uuid) and d.status in ('published', 'inconclusive')"
            " and d.requires_human_review"
            " and d.published_at < now() - make_interval(mins => :m)"
            " and d.published_at > now() - interval '7 days'"
            " and not exists (select 1 from doctor.diagnosis_feedback f"
            "  where f.tenant_id = d.tenant_id and f.diagnosis_id = d.id)"
            " order by d.published_at limit 50"
        ),
        {"t": rule.tenant_id, "m": rule.conditions.minutes},
    )
    return [
        (
            rule,
            Notice(
                f"diagnosis:{row.id}",
                Message(
                    "Diagnóstico aguardando revisão",
                    f"{row.title} · {row.name}"[:300],
                    f"{app_url()}/incidentes/{row.incident}",
                ),
                once=True,
            ),
        )
        for row in found
    ]
