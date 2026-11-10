"""Worker `notifier` (#41) contra Postgres real, com os envios trocados por fakes."""

import asyncio
import json
import os
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aid_alerts import Message
from aid_alerts.signing import verify
from aid_notifier import servicenow
from aid_notifier.channels import DeliveryError, PushTarget, Senders
from aid_notifier.jira import create_ticket, maintain, post_comment, sync
from aid_notifier.notify import evaluate, scan
from aid_notifier.webhooks import deliver
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
# 15:00 UTC = 12:00 em São Paulo (fora do silêncio 22:00 às 07:00); 05:00 UTC = 02:00 (dentro).
NOON = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
NIGHT = datetime(2026, 11, 10, 5, 0, tzinfo=UTC)
QUIET = {"start": "22:00", "end": "07:00", "timezone": "America/Sao_Paulo"}


class Fake:
    def __init__(self) -> None:
        self.pushes: list[tuple[str, Message]] = []
        self.webhooks: list[tuple[str, str, Message]] = []
        self.emails: list[tuple[list[str], str, str]] = []
        self.gone: set[str] = set()

    def senders(self) -> Senders:
        fake = self

        async def push(target: PushTarget, message: Message) -> bool:
            if target.endpoint in fake.gone:
                return False
            fake.pushes.append((target.endpoint, message))
            return True

        async def webhook(kind: str, url: str, message: Message) -> None:
            if "falha" in url:
                raise DeliveryError("o slack respondeu HTTP 500")
            fake.webhooks.append((kind, url, message))

        class Mailer:
            def send(self, to: Sequence[str], subject: str, body: str) -> None:
                fake.emails.append((list(to), subject, body))

        return Senders(webhook=webhook, push=push, mailer=Mailer)


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


async def rows(engine: AsyncEngine, sql: str, **params: Any) -> list[Any]:
    async with engine.begin() as connection:
        return list((await connection.execute(text(sql), params)).mappings())


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


@pytest_asyncio.fixture
async def org(engine: AsyncEngine) -> AsyncIterator[dict[str, str]]:
    ids = {name: str(uuid4()) for name in ("tenant", "integration", "admin", "analyst")}
    await run(
        engine,
        "insert into auth.users (id, instance_id, aud, role, email) values"
        " (:a, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :ea),"
        " (:n, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :en)",
        a=ids["admin"],
        n=ids["analyst"],
        ea=f"plantao-{ids['admin'][:8]}@acme.test",
        en=f"analista-{ids['analyst'][:8]}@acme.test",
    )
    await run(
        engine,
        "insert into public.organizations (id, name, slug) values (:t, 'Acme', :s)",
        t=ids["tenant"],
        s=f"acme-{ids['tenant'][:8]}",
    )
    await run(engine, "insert into doctor.tenants (id) values (:t)", t=ids["tenant"])
    await run(
        engine,
        "insert into public.organization_members (org_id, user_id, role)"
        " values (:t, :a, 'member'), (:t, :n, 'member')",
        t=ids["tenant"],
        a=ids["admin"],
        n=ids["analyst"],
    )
    await run(
        engine,
        "insert into doctor.memberships (tenant_id, user_id, role)"
        " values (:t, :a, 'admin'), (:t, :n, 'analyst')",
        t=ids["tenant"],
        a=ids["admin"],
        n=ids["analyst"],
    )
    await run(
        engine,
        "insert into doctor.integrations (id, tenant_id, name, source_system, target_system,"
        " environment) values (:i, :t, 'Pedidos SF → SAP', 'salesforce', 'sap', 'prd')",
        i=ids["integration"],
        t=ids["tenant"],
    )
    yield ids
    for table in (
        "notification_deliveries",
        "webhook_deliveries",
        "webhooks",
        "incident_comments",
        "incident_tickets",
        "itsm_connections",
        "alert_rules",
        "push_subscriptions",
        "alert_preferences",
        "incidents",
        "executions",
        "connectors",
        "outbox_messages",
        "integrations",
    ):
        await run(engine, f"delete from doctor.{table} where tenant_id = :t", t=ids["tenant"])  # noqa: S608
    await run(
        engine,
        "delete from vault.secrets where id in (select secret_id from doctor.notification_channels"
        " where tenant_id = :t)",
        t=ids["tenant"],
    )
    await run(
        engine, "delete from doctor.notification_channels where tenant_id = :t", t=ids["tenant"]
    )
    await run(engine, "delete from doctor.memberships where tenant_id = :t", t=ids["tenant"])
    await run(engine, "delete from public.organization_members where org_id = :t", t=ids["tenant"])
    await run(engine, "delete from doctor.incident_counters where tenant_id = :t", t=ids["tenant"])
    await run(engine, "delete from doctor.tenants where id = :t", t=ids["tenant"])
    await run(engine, "delete from public.organizations where id = :t", t=ids["tenant"])
    await run(
        engine,
        "delete from auth.users where id = any(cast(:u as uuid[]))",
        u=[ids["admin"], ids["analyst"]],
    )


async def channel(engine: AsyncEngine, org: dict[str, str], kind: str, **extra: Any) -> str:
    channel_id = str(uuid4())
    secret = extra.get("webhook")
    await run(
        engine,
        "insert into doctor.notification_channels (id, tenant_id, type, name, config, secret_id)"
        " values (cast(:c as uuid), :t, :k, :n, cast(:cfg as jsonb),"
        " case when cast(:w as text) is null then null"
        " else vault.create_secret(cast(:w as text), 'doctor/channel/' || cast(:c as text)) end)",
        c=channel_id,
        t=org["tenant"],
        k=kind,
        n=f"{kind}-{channel_id[:6]}",
        cfg=json.dumps(extra.get("config", {})),
        w=secret,
    )
    return channel_id


async def rule(
    engine: AsyncEngine,
    org: dict[str, str],
    conditions: dict[str, Any],
    channels: list[str],
    quiet: dict[str, str] | None = None,
) -> str:
    rule_id = str(uuid4())
    await run(
        engine,
        "insert into doctor.alert_rules (id, tenant_id, name, conditions, channels, quiet_hours)"
        " values (:r, :t, :n, cast(:c as jsonb), cast(:ch as jsonb), cast(:q as jsonb))",
        r=rule_id,
        t=org["tenant"],
        n=f"Regra {rule_id[:6]}",
        c=json.dumps(conditions),
        ch=json.dumps(channels),
        q=json.dumps(quiet) if quiet else None,
    )
    return rule_id


async def incident(engine: AsyncEngine, org: dict[str, str], severity: str) -> str:
    incident_id = str(uuid4())
    await run(
        engine,
        "insert into doctor.incidents (id, tenant_id, integration_id, title, category, severity,"
        " rule_code, rule_version, first_seen_at, last_seen_at) values (:i, :t, :g,"
        " 'Timeout na criação de pedidos', 'TIMEOUT', :s, 'INT-003', '2026.10.1', now(), now())",
        i=incident_id,
        t=org["tenant"],
        g=org["integration"],
        s=severity,
    )
    return incident_id


async def subscribe(engine: AsyncEngine, org: dict[str, str], user: str, endpoint: str) -> None:
    await run(
        engine,
        "insert into doctor.push_subscriptions (tenant_id, user_id, endpoint, p256dh, auth)"
        " values (:t, :u, :e, repeat('p', 87), repeat('a', 22))",
        t=org["tenant"],
        u=user,
        e=endpoint,
    )


@pytest.mark.asyncio
async def test_37_execucoes_no_mesmo_incidente_critico_geram_1_push(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    push = await channel(engine, org, "webpush", config={"audience": "managers"})
    await rule(
        engine,
        org,
        {"type": "incident", "min_severity": "critical", "environments": ["prd"]},
        [push],
    )
    await subscribe(engine, org, org["admin"], "https://fcm.googleapis.com/fcm/send/celular")
    await subscribe(engine, org, org["analyst"], "https://fcm.googleapis.com/fcm/send/analista")
    found = await incident(engine, org, "critical")
    fake = Fake()
    payloads = [{"source": "incident.opened", "incident_id": found}] + [
        {"source": "incident.updated", "incident_id": found} for _ in range(36)
    ]
    # Entregas concorrentes, como no Pub/Sub, e de madrugada: o crítico fura o silêncio.
    results = await asyncio.gather(
        *(evaluate(engine, payload, fake.senders(), NIGHT) for payload in payloads)
    )
    assert sum(results) == 1
    # Só o público do canal (gestores): o analista não recebe.
    assert [endpoint for endpoint, _ in fake.pushes] == [
        "https://fcm.googleapis.com/fcm/send/celular"
    ]
    _, message = fake.pushes[0]
    assert message.url.endswith(f"/incidentes/{found}")
    assert "Timeout na criação de pedidos" in message.body
    statuses = await rows(
        engine,
        "select status, count(*) as n from doctor.notification_deliveries"
        " where tenant_id = cast(:t as uuid) group by status order by status",
        t=org["tenant"],
    )
    assert {r["status"]: r["n"] for r in statuses} == {"sent": 1, "suppressed": 36}


@pytest.mark.asyncio
async def test_silencio_segura_o_que_nao_e_critico_e_15_min_depois_notifica_de_novo(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    slack = await channel(engine, org, "slack", webhook="https://hooks.slack.com/services/T/B/x")
    await rule(engine, org, {"type": "incident", "min_severity": "high"}, [slack], QUIET)
    found = await incident(engine, org, "high")
    fake = Fake()
    payload = {"source": "incident.opened", "incident_id": found}
    assert await evaluate(engine, payload, fake.senders(), NIGHT) == 0
    assert await evaluate(engine, payload, fake.senders(), NOON) == 1
    assert [kind for kind, _, _ in fake.webhooks] == ["slack"]
    assert await evaluate(engine, payload, fake.senders(), NOON) == 0
    await run(
        engine,
        "update doctor.notification_deliveries set created_at = now() - interval '16 minutes'"
        " where tenant_id = cast(:t as uuid)",
        t=org["tenant"],
    )
    assert await evaluate(engine, payload, fake.senders(), NOON) == 1


@pytest.mark.asyncio
async def test_falha_no_canal_fica_no_historico_e_nao_bloqueia_a_proxima(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    broken = await channel(engine, org, "slack", webhook="https://hooks.slack.com/services/falha")
    await rule(engine, org, {"type": "incident", "min_severity": "low"}, [broken])
    found = await incident(engine, org, "medium")
    fake = Fake()
    payload = {"source": "incident.opened", "incident_id": found}
    assert await evaluate(engine, payload, fake.senders(), NOON) == 0
    [delivery] = await rows(
        engine,
        "select status, error from doctor.notification_deliveries"
        " where tenant_id = cast(:t as uuid)",
        t=org["tenant"],
    )
    assert dict(delivery) == {"status": "failed", "error": "o slack respondeu HTTP 500"}


@pytest.mark.asyncio
async def test_conector_em_failing_avisa_por_email_os_gestores(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    email = await channel(engine, org, "email", config={"audience": "managers"})
    await rule(engine, org, {"type": "connector_failing"}, [email])
    connector = str(uuid4())
    await run(
        engine,
        "insert into doctor.connectors (id, tenant_id, integration_id, provider, name, status)"
        " values (:c, :t, :i, 'gcp', 'Cloud Logging', 'failing')",
        c=connector,
        t=org["tenant"],
        i=org["integration"],
    )
    fake = Fake()
    payload = {"source": "connector.failing", "connector_id": connector}
    assert await evaluate(engine, payload, fake.senders(), NOON) == 1
    [(to, subject, body)] = fake.emails
    assert to == [f"plantao-{org['admin'][:8]}@acme.test"]
    assert subject == "Conector com falhas"
    assert "Cloud Logging · Pedidos SF → SAP" in body


@pytest.mark.asyncio
async def test_assinatura_que_expirou_e_apagada(engine: AsyncEngine, org: dict[str, str]) -> None:
    push = await channel(engine, org, "webpush", config={"audience": "all"})
    await rule(engine, org, {"type": "incident", "min_severity": "low"}, [push])
    await subscribe(engine, org, org["admin"], "https://fcm.googleapis.com/fcm/send/antigo")
    found = await incident(engine, org, "low")
    fake = Fake()
    fake.gone.add("https://fcm.googleapis.com/fcm/send/antigo")
    assert (
        await evaluate(
            engine, {"source": "incident.opened", "incident_id": found}, fake.senders(), NOON
        )
        == 0
    )
    left = await rows(
        engine,
        "select 1 from doctor.push_subscriptions where tenant_id = cast(:t as uuid)",
        t=org["tenant"],
    )
    assert left == []


@pytest.mark.asyncio
async def test_taxa_de_erro_acima_do_limite_na_varredura(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    teams = await channel(
        engine, org, "teams", webhook="https://acme.webhook.office.com/webhookb2/abc"
    )
    await rule(
        engine,
        org,
        {"type": "error_rate", "threshold_pct": 5, "minutes": 10, "min_executions": 10},
        [teams],
    )
    for n in range(20):
        await run(
            engine,
            "insert into doctor.executions (id, tenant_id, integration_id, status, first_event_at,"
            " last_event_at) values (:x, :t, :i, :s, :at, :at)",
            x=str(uuid4()),
            t=org["tenant"],
            i=org["integration"],
            s="failed" if n < 3 else "success",
            at=datetime.now(UTC) - timedelta(minutes=2),
        )
    fake = Fake()
    assert await scan(engine, fake.senders(), NOON) >= 1
    mine = [m for kind, _, m in fake.webhooks if kind == "teams" and "Pedidos SF → SAP" in m.body]
    assert mine[0].title == "Taxa de erro acima de 5%"
    assert "15% em 10 min" in mine[0].body


@pytest.mark.asyncio
async def test_regras_sobrepostas_no_mesmo_canal_notificam_uma_vez(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    push = await channel(engine, org, "webpush", config={"audience": "managers"})
    await rule(engine, org, {"type": "incident", "min_severity": "critical"}, [push])
    await rule(engine, org, {"type": "incident", "min_severity": "high"}, [push])
    await subscribe(engine, org, org["admin"], "https://fcm.googleapis.com/fcm/send/celular")
    found = await incident(engine, org, "critical")
    fake = Fake()
    assert (
        await evaluate(
            engine, {"source": "incident.opened", "incident_id": found}, fake.senders(), NOON
        )
        == 1
    )
    assert len(fake.pushes) == 1


@pytest.mark.asyncio
async def test_incidente_que_vira_critico_notifica_de_novo(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    slack = await channel(engine, org, "slack", webhook="https://hooks.slack.com/services/T/B/x")
    await rule(engine, org, {"type": "incident", "min_severity": "high"}, [slack])
    found = await incident(engine, org, "high")
    fake = Fake()
    payload = {"source": "incident.updated", "incident_id": found}
    assert await evaluate(engine, payload, fake.senders(), NOON) == 1
    await run(engine, "update doctor.incidents set severity = 'critical' where id = :i", i=found)
    assert await evaluate(engine, payload, fake.senders(), NOON) == 1
    assert [m.title.split(" #")[0] for _, _, m in fake.webhooks] == [
        "Incidente atualizado alta",
        "Incidente atualizado crítico",
    ]


@pytest.mark.asyncio
async def test_canal_que_quebra_nao_impede_os_outros_e_espera_antes_de_tentar_de_novo(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    broken = await channel(engine, org, "slack", webhook="https://hooks.slack.com/services/falha")
    email = await channel(engine, org, "email", config={"audience": "all"})
    await rule(engine, org, {"type": "incident", "min_severity": "low"}, [broken, email])
    found = await incident(engine, org, "medium")
    fake = Fake()
    payload = {"source": "incident.updated", "incident_id": found}
    assert await evaluate(engine, payload, fake.senders(), NOON) == 1
    # Um e-mail por pessoa: ninguém vê o endereço do colega.
    assert sorted(len(to) for to, _, _ in fake.emails) == [1, 1]
    # O Slack quebrado espera 5 min; o e-mail, os 15 min da deduplicação.
    assert await evaluate(engine, payload, fake.senders(), NOON) == 0
    statuses = await rows(
        engine,
        "select status, count(*) as n from doctor.notification_deliveries"
        " where tenant_id = cast(:t as uuid) group by status order by status",
        t=org["tenant"],
    )
    assert {r["status"]: r["n"] for r in statuses} == {"failed": 1, "sent": 1, "suppressed": 2}


@pytest.mark.asyncio
async def test_falha_inesperada_no_canal_vira_failed_e_nao_some(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    push = await channel(engine, org, "webpush", config={"audience": "managers"})
    await rule(engine, org, {"type": "incident", "min_severity": "low"}, [push])
    await subscribe(engine, org, org["admin"], "https://fcm.googleapis.com/fcm/send/x")
    found = await incident(engine, org, "low")

    async def explode(target: PushTarget, message: Message) -> bool:
        raise TimeoutError("rede")

    senders = Fake().senders()
    senders.push = explode
    payload = {"source": "incident.opened", "incident_id": found}
    assert await evaluate(engine, payload, senders, NOON) == 0
    [delivery] = await rows(
        engine,
        "select status from doctor.notification_deliveries where tenant_id = cast(:t as uuid)",
        t=org["tenant"],
    )
    assert delivery["status"] == "failed"


SECRET = "whsec_segredo-de-teste"  # noqa: S105 - segredo de teste


async def webhook(engine: AsyncEngine, org: dict[str, str], events: list[str]) -> str:
    webhook_id = str(uuid4())
    await run(
        engine,
        "insert into doctor.webhooks (id, tenant_id, name, url, events, secret_id) values"
        " (cast(:w as uuid), :t, :n, 'https://itsm.acme.com.br/aid', cast(:e as text[]),"
        " vault.create_secret(:s, 'doctor/webhook/' || cast(:w as text)))",
        w=webhook_id,
        t=org["tenant"],
        n=f"ITSM {webhook_id[:6]}",
        e=events,
        s=SECRET,
    )
    return webhook_id


class Receiver:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(self.status, text="ok" if self.status < 300 else "erro do ITSM")

        return httpx.MockTransport(handle)


async def deliveries(engine: AsyncEngine, org: dict[str, str]) -> list[Any]:
    return await rows(
        engine,
        "select id::text, status, attempts, response_status, error, body,"
        " next_attempt_at > now() + interval '50 seconds' as later"
        " from doctor.webhook_deliveries where tenant_id = cast(:t as uuid) order by created_at",
        t=org["tenant"],
    )


@pytest.mark.asyncio
async def test_incidente_aberto_chega_assinado_e_sem_eventos_brutos(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    await webhook(engine, org, ["incident.opened"])
    found = await incident(engine, org, "critical")
    [pending] = await deliveries(engine, org)
    receiver = Receiver()
    status = await deliver(engine, pending["id"], Fake().senders(), receiver.transport())
    assert status == "succeeded"
    [request] = receiver.requests
    assert verify(SECRET, request.headers["x-aid-signature"], request.content)
    assert request.headers["x-aid-event"] == "incident.opened"
    body = json.loads(request.content)
    assert body["version"] == "webhook.v1"
    assert body["data"]["incident"]["id"] == found
    assert body["data"]["incident"]["url"].endswith(f"/incidentes/{found}")
    assert "events" not in json.dumps(body)
    [done] = await deliveries(engine, org)
    assert (done["status"], done["response_status"]) == ("succeeded", 200)
    # Entregue não se entrega de novo (mensagem repetida do Pub/Sub).
    assert await deliver(engine, pending["id"], Fake().senders(), receiver.transport()) == "skipped"


@pytest.mark.asyncio
async def test_falha_tenta_de_novo_depois_e_reenviar_usa_o_mesmo_corpo(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    await webhook(engine, org, ["incident.opened"])
    await incident(engine, org, "high")
    [pending] = await deliveries(engine, org)
    receiver = Receiver(503)
    assert await deliver(engine, pending["id"], Fake().senders(), receiver.transport()) == "pending"
    [retry] = await deliveries(engine, org)
    assert (retry["attempts"], retry["response_status"], retry["error"]) == (1, 503, "HTTP 503")
    assert retry["later"]
    # Ainda não venceu: a varredura não tenta antes da hora.
    assert await deliver(engine, pending["id"], Fake().senders(), receiver.transport()) == "skipped"
    await run(
        engine,
        "update doctor.webhook_deliveries set created_at = now() - interval '25 hours',"
        " next_attempt_at = now() where id = cast(:d as uuid)",
        d=pending["id"],
    )
    assert (
        await deliver(engine, pending["id"], Fake().senders(), receiver.transport()) == "abandoned"
    )
    original = (await deliveries(engine, org))[0]
    await run(
        engine,
        "insert into doctor.webhook_deliveries (tenant_id, webhook_id, event, subject, body,"
        " resent_from) select tenant_id, webhook_id, event, subject, body, id"
        " from doctor.webhook_deliveries where id = cast(:d as uuid)",
        d=original["id"],
    )
    resent = await rows(
        engine,
        "select id::text from doctor.webhook_deliveries where resent_from = cast(:d as uuid)",
        d=original["id"],
    )
    ok = Receiver()
    assert await deliver(engine, resent[0]["id"], Fake().senders(), ok.transport()) == "succeeded"
    assert json.loads(ok.requests[0].content)["id"] == original["id"]


@pytest.mark.asyncio
async def test_50_falhas_seguidas_desligam_e_avisam_os_admins(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    hook = await webhook(engine, org, ["incident.opened"])
    await run(
        engine, "update doctor.webhooks set failure_count = 49 where id = cast(:w as uuid)", w=hook
    )
    await incident(engine, org, "high")
    [pending] = await deliveries(engine, org)
    fake = Fake()
    assert (
        await deliver(engine, pending["id"], fake.senders(), Receiver(500).transport())
        == "abandoned"
    )
    [state] = await rows(
        engine,
        "select enabled, failure_count, disabled_reason from doctor.webhooks"
        " where id = cast(:w as uuid)",
        w=hook,
    )
    assert dict(state) == {
        "enabled": False,
        "failure_count": 50,
        "disabled_reason": "50 falhas seguidas",
    }
    [(to, subject, _)] = fake.emails
    assert to == [f"plantao-{org['admin'][:8]}@acme.test"]
    assert subject == "Webhook desligado após 50 falhas seguidas"


@pytest.mark.asyncio
async def test_corpo_e_o_retrato_da_hora_do_evento(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    """Resolvido antes da primeira tentativa: o `incident.opened` chega como aberto."""
    await webhook(engine, org, ["incident.opened"])
    found = await incident(engine, org, "high")
    await run(
        engine,
        "update doctor.incidents set status = 'resolved', resolved_at = now(),"
        " resolution_note = 'ajustado' where id = :i",
        i=found,
    )
    [pending] = await deliveries(engine, org)
    receiver = Receiver()
    assert (
        await deliver(engine, pending["id"], Fake().senders(), receiver.transport()) == "succeeded"
    )
    body = json.loads(receiver.requests[0].content)
    assert body["data"]["incident"]["status"] == "open"


@pytest.mark.asyncio
async def test_resposta_com_nul_e_gigante_nao_trava_a_entrega(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    await webhook(engine, org, ["incident.opened"])
    await incident(engine, org, "high")
    [pending] = await deliveries(engine, org)

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"ok\x00" + b"x" * 5_000_000)

    status = await deliver(engine, pending["id"], Fake().senders(), httpx.MockTransport(handle))
    assert status == "succeeded"
    [done] = await rows(
        engine,
        "select status, char_length(response_excerpt) as size from doctor.webhook_deliveries"
        " where id = cast(:d as uuid)",
        d=pending["id"],
    )
    assert done["status"] == "succeeded"
    assert done["size"] <= 1024


@pytest.mark.asyncio
async def test_segredo_sumido_conta_como_falha_e_nao_fica_preso(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    hook = await webhook(engine, org, ["incident.opened"])
    await incident(engine, org, "high")
    await run(
        engine,
        "delete from vault.secrets where id = (select secret_id from doctor.webhooks"
        " where id = cast(:w as uuid))",
        w=hook,
    )
    [pending] = await deliveries(engine, org)
    assert (
        await deliver(engine, pending["id"], Fake().senders(), Receiver().transport()) == "pending"
    )
    [retry] = await deliveries(engine, org)
    assert (retry["attempts"], retry["error"]) == (1, "falha interna na entrega")


class FakeJira:
    """Atlassian falso: token, criação de issue, leitura com status e comentários, webhook."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.refreshes = 0
        self.webhooks: list[dict[str, Any]] = []
        self.status = {"name": "Em atendimento", "statusCategory": {"key": "indeterminate"}}
        self.jira_comments: list[dict[str, Any]] = []
        self.refresh_status = 200
        self.existing: list[dict[str, Any]] = []
        self.deleted: list[Any] = []
        self.reads: list[str] = []
        self.webhook_result: dict[str, Any] = {"createdWebhookId": 7}
        self.crash = False

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if self.crash:
                raise RuntimeError("falha inesperada")
            if request.url.host == "auth.atlassian.com":
                self.refreshes += 1
                if self.refresh_status != 200:
                    return httpx.Response(self.refresh_status, json={"error": "invalid_grant"})
                return httpx.Response(
                    200,
                    json={"access_token": "novo", "refresh_token": "girado", "expires_in": 3600},
                )
            if path.endswith("/rest/api/3/search/jql"):
                return httpx.Response(200, json={"issues": self.existing})
            if path.endswith("/rest/api/3/webhook") and request.method == "DELETE":
                self.deleted.extend(json.loads(request.content)["webhookIds"])
                return httpx.Response(202)
            if path.endswith("/rest/api/3/issue") and request.method == "POST":
                self.created.append(json.loads(request.content))
                return httpx.Response(201, json={"id": "10042", "key": "SUST-881"})
            if path.endswith("/rest/api/3/webhook") and request.method == "POST":
                self.webhooks.append(json.loads(request.content))
                return httpx.Response(
                    200, json={"webhookRegistrationResult": [self.webhook_result]}
                )
            if path.endswith("/comment") and request.method == "POST":
                self.comments.append(json.loads(request.content))
                return httpx.Response(201, json={"id": "c1"})
            if "/rest/api/3/issue/SUST-" in path:
                self.reads.append(path.rsplit("/", 1)[-1])
                return httpx.Response(
                    200,
                    json={
                        "fields": {
                            "status": self.status,
                            "comment": {"comments": self.jira_comments},
                        }
                    },
                )
            return httpx.Response(404)

        return httpx.MockTransport(handle)


async def jira_connection(
    engine: AsyncEngine, org: dict[str, str], *, expires_in: float = 3600
) -> str:
    connection = str(uuid4())
    tokens = {
        "access_token": "valido",
        "refresh_token": "r1",
        "expires_at": __import__("time").time() + expires_in,
        "hook_token": "tok",
    }
    await run(
        engine,
        "insert into doctor.itsm_connections (id, tenant_id, status, sites, cloud_id, site_url,"
        " project_key, issue_type, secret_id) values (cast(:c as uuid), :t, 'active',"
        " '[{\"id\": \"cloud-1\"}]', 'cloud-1', 'https://acme.atlassian.net', 'SUST',"
        " 'Incidente', vault.create_secret(:s, 'doctor/itsm/' || cast(:c as text)))",
        c=connection,
        t=org["tenant"],
        s=json.dumps(tokens),
    )
    return connection


async def ticket_rows(engine: AsyncEngine, org: dict[str, str]) -> list[Any]:
    return await rows(
        engine,
        "select id::text, status, external_key, url, external_status, error"
        " from doctor.incident_tickets where tenant_id = cast(:t as uuid)",
        t=org["tenant"],
    )


@pytest.mark.asyncio
async def test_incidente_critico_com_regra_automatica_abre_o_chamado_uma_vez(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    """Critério do #43: a Regra dispara de novo e alguém pede à mão; o chamado é um só."""
    await jira_connection(engine, org)
    jira_channel = await channel(engine, org, "jira")
    await rule(engine, org, {"type": "incident", "min_severity": "critical"}, [jira_channel])
    found = await incident(engine, org, "critical")
    fake = Fake()
    for source in ("incident.opened", "incident.updated", "incident.updated"):
        await evaluate(engine, {"source": source, "incident_id": found}, fake.senders(), NOON)
    await run(
        engine,
        "select doctor.queue_ticket(cast(:t as uuid), cast(:i as uuid), null, null)",
        t=org["tenant"],
        i=found,
    )
    [ticket] = await ticket_rows(engine, org)
    assert ticket["status"] == "creating"
    requested = await rows(
        engine,
        "select count(*) as n from doctor.outbox_messages where topic = 'itsm.ticket'"
        " and tenant_id = cast(:t as uuid)",
        t=org["tenant"],
    )
    assert requested[0]["n"] == 1
    jira = FakeJira()
    assert await create_ticket(engine, ticket["id"], jira.transport()) == "open"
    assert await create_ticket(engine, ticket["id"], jira.transport()) == "skipped"
    [created] = jira.created
    fields = created["fields"]
    assert (fields["project"], fields["priority"], fields["labels"]) == (
        {"key": "SUST"},
        {"name": "Highest"},
        ["integration-ai-doctor", f"aid-{ticket['id']}"],
    )
    text_body = json.dumps(fields["description"], ensure_ascii=False)
    assert f"/incidentes/{found}" in text_body
    assert "Diagnóstico ainda não publicado." in text_body
    [done] = await ticket_rows(engine, org)
    assert (done["status"], done["external_key"], done["url"]) == (
        "open",
        "SUST-881",
        "https://acme.atlassian.net/browse/SUST-881",
    )


@pytest.mark.asyncio
async def test_corpo_leva_causa_com_confianca_heuristica_e_recomendacoes(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    await jira_connection(engine, org)
    found = await incident(engine, org, "high")
    diagnosis = str(uuid4())
    await run(
        engine,
        "insert into doctor.diagnoses (id, tenant_id, incident_id, version, requested_mode, mode,"
        " processing_key, status, stage, classification, probable_cause, confidence)"
        " values (cast(:d as uuid), :t, :i, 1, 'rules_only', 'rules_only', :k, 'running',"
        " 'verification', 'UPSTREAM_TIMEOUT', 'O SAP não respondeu a tempo.', 0.68)",
        d=diagnosis,
        t=org["tenant"],
        i=found,
        k=f"k-{diagnosis}",
    )
    await run(
        engine,
        "insert into doctor.diagnosis_recommendations (tenant_id, diagnosis_id, rank, text, kind)"
        " values (:t, cast(:d as uuid), 1, 'Confirme no SAP se o pedido existe.', 'verify')",
        t=org["tenant"],
        d=diagnosis,
    )
    await run(
        engine,
        "update doctor.diagnoses set status = 'published', stage = 'done', published_at = now()"
        " where id = cast(:d as uuid)",
        d=diagnosis,
    )
    await run(
        engine,
        "select doctor.queue_ticket(cast(:t as uuid), cast(:i as uuid), null, null)",
        t=org["tenant"],
        i=found,
    )
    [ticket] = await ticket_rows(engine, org)
    jira = FakeJira()
    await create_ticket(engine, ticket["id"], jira.transport())
    text_body = json.dumps(jira.created[0]["fields"]["description"], ensure_ascii=False)
    assert "Confiança heurística: 0,68" in text_body
    assert "O SAP não respondeu a tempo." in text_body
    assert "Confirme no SAP se o pedido existe." in text_body


@pytest.mark.asyncio
async def test_resolvido_no_jira_e_comentario_com_prefixo_voltam_uma_vez(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    connection = await jira_connection(engine, org)
    found = await incident(engine, org, "high")
    await run(
        engine,
        "insert into doctor.incident_tickets (tenant_id, incident_id, status, external_key)"
        " values (:t, :i, 'open', 'SUST-881')",
        t=org["tenant"],
        i=found,
    )
    jira = FakeJira()
    jira.status = {"name": "Resolvido", "statusCategory": {"key": "done"}}
    jira.jira_comments = [
        {
            "id": "9",
            "author": {"displayName": "Ana (N1)"},
            "body": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "#doctor reprocessado com o lote corrigido"}
                        ],
                    }
                ],
            },
        },
        {
            "id": "10",
            "author": {"displayName": "Bot"},
            "body": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "interno, sem prefixo"}],
                    }
                ],
            },
        },
    ]
    for _ in range(2):
        await sync(engine, {"connection_id": connection}, jira.transport())
    [ticket] = await ticket_rows(engine, org)
    assert (ticket["status"], ticket["external_status"]) == ("done", "Resolvido")
    comments = await rows(
        engine,
        "select body_md, external_author from doctor.incident_comments"
        " where incident_id = cast(:i as uuid)",
        i=found,
    )
    assert [dict(c) for c in comments] == [
        {
            "body_md": "Do Jira (SUST-881): reprocessado com o lote corrigido",
            "external_author": "Ana (N1)",
        }
    ]
    # O Incidente não é resolvido sozinho: a tela sugere, e uma pessoa confirma.
    [state] = await rows(engine, "select status from doctor.incidents where id = :i", i=found)
    assert state["status"] == "open"


@pytest.mark.asyncio
async def test_token_vencido_renova_e_recusado_pede_nova_conexao(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    connection = await jira_connection(engine, org, expires_in=-10)
    found = await incident(engine, org, "high")
    await run(
        engine,
        "insert into doctor.incident_tickets (tenant_id, incident_id, status, external_key)"
        " values (:t, :i, 'open', 'SUST-881')",
        t=org["tenant"],
        i=found,
    )
    jira = FakeJira()
    await sync(engine, {"connection_id": connection, "register": True}, jira.transport())
    assert jira.refreshes == 1
    assert jira.webhooks[0]["url"].endswith("/api/v1/itsm/jira/hooks/tok")
    stored = await rows(
        engine,
        "select doctor.get_itsm_tokens(cast(:c as uuid)) as t, jira_webhook_id"
        " from doctor.itsm_connections where id = cast(:c as uuid)",
        c=connection,
    )
    assert json.loads(stored[0]["t"])["refresh_token"] == "girado"  # noqa: S105 - token falso
    assert stored[0]["jira_webhook_id"] == 7
    await run(
        engine,
        "select doctor.put_itsm_tokens(cast(:c as uuid), :t)",
        c=connection,
        t=json.dumps({"access_token": "x", "refresh_token": "y", "expires_at": 0}),
    )
    jira.refresh_status = 400
    await sync(engine, {"connection_id": connection}, jira.transport())
    [state] = await rows(
        engine,
        "select status from doctor.itsm_connections where id = cast(:c as uuid)",
        c=connection,
    )
    assert state["status"] == "needs_reauth"


@pytest.mark.asyncio
async def test_comentario_com_jira_vai_para_o_chamado(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    await jira_connection(engine, org)
    found = await incident(engine, org, "high")
    await run(
        engine,
        "insert into doctor.incident_tickets (tenant_id, incident_id, status, external_key)"
        " values (:t, :i, 'open', 'SUST-881')",
        t=org["tenant"],
        i=found,
    )
    await run(
        engine,
        "insert into doctor.incident_comments (tenant_id, incident_id, author_id, body_md)"
        " values (:t, :i, :u, '#jira Timeout ajustado para 60 s no gateway.')",
        t=org["tenant"],
        i=found,
        u=org["admin"],
    )
    [queued] = await rows(
        engine,
        "select payload from doctor.outbox_messages where topic = 'itsm.comment'"
        " and tenant_id = cast(:t as uuid)",
        t=org["tenant"],
    )
    jira = FakeJira()
    assert await post_comment(engine, queued["payload"], jira.transport())
    text_body = json.dumps(jira.comments[0], ensure_ascii=False)
    assert "Timeout ajustado para 60 s no gateway." in text_body
    assert "#jira" not in text_body


async def open_ticket(engine: AsyncEngine, org: dict[str, str], incident_id: str, key: str) -> None:
    await run(
        engine,
        "insert into doctor.incident_tickets (tenant_id, incident_id, status, external_key)"
        " values (:t, :i, 'open', :k)",
        t=org["tenant"],
        i=incident_id,
        k=key,
    )


async def creating_ticket(engine: AsyncEngine, org: dict[str, str]) -> str:
    await jira_connection(engine, org)
    found = await incident(engine, org, "high")
    await run(
        engine,
        "select doctor.queue_ticket(cast(:t as uuid), cast(:i as uuid), null, null)",
        t=org["tenant"],
        i=found,
    )
    [ticket] = await ticket_rows(engine, org)
    return str(ticket["id"])


@pytest.mark.asyncio
async def test_entrega_repetida_nao_duplica_a_issue(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    """Pub/Sub entrega duas vezes: a segunda, enquanto a primeira está no ar, não cria; e uma
    nova tentativa depois de a issue existir adota a issue achada pelo rótulo do chamado."""
    ticket = await creating_ticket(engine, org)
    jira = FakeJira()
    await run(
        engine,
        "update doctor.incident_tickets set claimed_at = now() where id = cast(:t as uuid)",
        t=ticket,
    )
    assert await create_ticket(engine, ticket, jira.transport()) == "skipped"
    await run(
        engine,
        "update doctor.incident_tickets set claimed_at = now() - interval '6 minutes'"
        " where id = cast(:t as uuid)",
        t=ticket,
    )
    jira.existing = [{"id": "10042", "key": "SUST-881"}]
    assert await create_ticket(engine, ticket, jira.transport()) == "open"
    assert jira.created == []
    [row] = await ticket_rows(engine, org)
    assert row["external_key"] == "SUST-881"


@pytest.mark.asyncio
async def test_falha_inesperada_nao_prende_o_chamado_e_a_varredura_retoma(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    ticket = await creating_ticket(engine, org)
    jira = FakeJira()
    jira.crash = True
    assert await create_ticket(engine, ticket, jira.transport()) == "failed"
    [row] = await ticket_rows(engine, org)
    assert (row["status"], row["error"]) == ("failed", "falha interna ao abrir o chamado")
    # Preso em "criando" (o worker caiu): a varredura cria depois de 5 min.
    await run(
        engine,
        "update doctor.incident_tickets set status = 'creating', claimed_at = now()"
        " - interval '6 minutes' where id = cast(:t as uuid)",
        t=ticket,
    )
    jira.crash = False
    await maintain(engine, jira.transport())
    [row] = await ticket_rows(engine, org)
    assert row["status"] == "open"
    assert f"aid-{ticket}" in jira.created[0]["fields"]["labels"]


@pytest.mark.asyncio
async def test_registro_com_autorizacao_recusada_mantem_o_pedido_de_nova_conexao(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    connection = await jira_connection(engine, org, expires_in=-10)
    await open_ticket(engine, org, await incident(engine, org, "high"), "SUST-881")
    jira = FakeJira()
    jira.refresh_status = 400
    await sync(engine, {"connection_id": connection, "register": True}, jira.transport())
    [state] = await rows(
        engine,
        "select status from doctor.itsm_connections where id = cast(:c as uuid)",
        c=connection,
    )
    assert state["status"] == "needs_reauth"
    assert jira.refreshes == 1


@pytest.mark.asyncio
async def test_novo_registro_tira_o_webhook_antigo_e_guarda_o_erro_do_jira(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    connection = await jira_connection(engine, org)
    await run(
        engine,
        "update doctor.itsm_connections set jira_webhook_id = 3 where id = cast(:c as uuid)",
        c=connection,
    )
    jira = FakeJira()
    jira.webhook_result = {"errors": ["limite de webhooks"]}
    await sync(engine, {"connection_id": connection, "register": True}, jira.transport())
    [state] = await rows(
        engine,
        "select status, last_error from doctor.itsm_connections where id = cast(:c as uuid)",
        c=connection,
    )
    assert jira.deleted == [3]
    assert state["status"] == "active"
    assert "limite de webhooks" in state["last_error"]


@pytest.mark.asyncio
async def test_evento_do_jira_rele_so_a_issue_dele(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    connection = await jira_connection(engine, org)
    for key in ("SUST-881", "SUST-882", "SUST-883"):
        await open_ticket(engine, org, await incident(engine, org, "high"), key)
    jira = FakeJira()
    await sync(engine, {"connection_id": connection, "issue_key": "SUST-882"}, jira.transport())
    assert jira.reads == ["SUST-882"]


class FakeServiceNow:
    """Instância falsa: token por client credentials, Table API de incident."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.existing: list[dict[str, Any]] = []
        self.state = {"value": "2", "display_value": "In Progress"}
        self.token_status = 200
        self.reads: list[str] = []
        self.groups = {"SAP Basis": "1" * 32, "Service Desk": "2" * 32, "CRM": "3" * 32}
        self.read_status = 200

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "acme.service-now.com"
            path = request.url.path
            if path == "/oauth_token.do":
                if self.token_status != 200:
                    return httpx.Response(self.token_status, json={"error": "invalid_client"})
                return httpx.Response(200, json={"access_token": "sn", "expires_in": 1800})
            assert request.headers["authorization"] == "Bearer sn"
            if path == "/api/now/table/sys_user_group":
                name = request.url.params["sysparm_query"].removeprefix("name=")
                found = [{"sys_id": self.groups[name]}] if name in self.groups else []
                return httpx.Response(200, json={"result": found})
            if path == "/api/now/table/incident" and request.method == "GET":
                return httpx.Response(200, json={"result": self.existing})
            if path == "/api/now/table/incident" and request.method == "POST":
                assert "sysparm_input_display_value" not in request.url.params
                self.created.append(json.loads(request.content))
                return httpx.Response(
                    201, json={"result": {"sys_id": "a" * 32, "number": "INC0010001"}}
                )
            if path.startswith("/api/now/table/incident/"):
                self.reads.append(path.rsplit("/", 1)[-1])
                if self.read_status != 200:
                    return httpx.Response(
                        self.read_status, json={"error": {"message": "No Record"}}
                    )
                return httpx.Response(200, json={"result": {"state": self.state}})
            return httpx.Response(404)

        return httpx.MockTransport(handle)


async def servicenow_connection(engine: AsyncEngine, org: dict[str, str]) -> str:
    connection = str(uuid4())
    await run(
        engine,
        "insert into doctor.itsm_connections (id, tenant_id, provider, status, instance_url,"
        " client_id, assignment_groups, default_group, secret_id) values (cast(:c as uuid), :t,"
        " 'servicenow', 'active', 'https://acme.service-now.com', 'app',"
        ' \'{"sap": "SAP Basis", "salesforce": "CRM"}\', \'Service Desk\','
        " vault.create_secret('{\"client_secret\": \"s3\"}', 'doctor/sn/' || cast(:c as text)))",
        c=connection,
        t=org["tenant"],
    )
    return connection


async def servicenow_ticket(engine: AsyncEngine, org: dict[str, str], system: str | None) -> str:
    found = await incident(engine, org, "critical")
    if system is not None:
        diagnosis = str(uuid4())
        await run(
            engine,
            "insert into doctor.diagnoses (id, tenant_id, incident_id, version, requested_mode,"
            " mode, processing_key, status, stage, classification, probable_cause, confidence,"
            " responsible_system) values (cast(:d as uuid), :t, :i, 1, 'rules_only',"
            " 'rules_only', :k, 'running', 'verification', 'UPSTREAM_TIMEOUT',"
            " 'O SAP não respondeu a tempo.', 0.68, :s)",
            d=diagnosis,
            t=org["tenant"],
            i=found,
            k=f"k-{diagnosis}",
            s=system,
        )
        await run(
            engine,
            "update doctor.diagnoses set status = 'published', stage = 'done',"
            " published_at = now() where id = cast(:d as uuid)",
            d=diagnosis,
        )
    await run(
        engine,
        "select doctor.queue_ticket(cast(:t as uuid), cast(:i as uuid), null, null, 'servicenow')",
        t=org["tenant"],
        i=found,
    )
    [ticket] = await rows(
        engine,
        "select id::text from doctor.incident_tickets where incident_id = cast(:i as uuid)",
        i=found,
    )
    return str(ticket["id"])


@pytest.mark.asyncio
async def test_sistema_responsavel_sap_vai_para_o_grupo_mapeado_para_sap(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    """Critério do #44."""
    await servicenow_connection(engine, org)
    ticket = await servicenow_ticket(engine, org, "sap")
    instance = FakeServiceNow()
    assert await create_ticket_any(engine, ticket, instance) == "open"
    [created] = instance.created
    # O grupo vai pelo sys_id; impact e urgency pelos valores crus.
    assert (created["assignment_group"], created["impact"], created["urgency"]) == (
        "1" * 32,
        "1",
        "1",
    )
    assert created["correlation_id"] == ticket
    assert "Confiança heurística: 0,68" in created["work_notes"]
    assert "Sistema responsável: SAP" in created["work_notes"]
    assert "/incidentes/" in created["work_notes"]
    [row] = await rows(
        engine,
        "select status, external_key, assignment_group, url from doctor.incident_tickets"
        " where id = cast(:t as uuid)",
        t=ticket,
    )
    assert (row["status"], row["external_key"], row["assignment_group"]) == (
        "open",
        "INC0010001",
        "SAP Basis",
    )
    assert row["url"].startswith("https://acme.service-now.com/nav_to.do?uri=incident.do")


async def create_ticket_any(engine: AsyncEngine, ticket: str, instance: FakeServiceNow) -> str:
    from aid_notifier.itsm import create_ticket as dispatch

    return await dispatch(engine, ticket, instance.transport())


@pytest.mark.asyncio
async def test_indeterminado_vai_para_o_grupo_padrao(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    await servicenow_connection(engine, org)
    instance = FakeServiceNow()
    for system in (None, "gcp"):
        ticket = await servicenow_ticket(engine, org, system)
        await create_ticket_any(engine, ticket, instance)
    assert [c["assignment_group"] for c in instance.created] == ["2" * 32, "2" * 32]
    assert "Diagnóstico ainda não publicado." in instance.created[0]["work_notes"]


@pytest.mark.asyncio
async def test_incident_ja_criado_e_adotado_pelo_correlation_id(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    await servicenow_connection(engine, org)
    ticket = await servicenow_ticket(engine, org, "sap")
    instance = FakeServiceNow()
    instance.existing = [{"sys_id": "b" * 32, "number": "INC0010009"}]
    assert await create_ticket_any(engine, ticket, instance) == "open"
    assert instance.created == []
    [row] = await rows(
        engine,
        "select external_key from doctor.incident_tickets where id = cast(:t as uuid)",
        t=ticket,
    )
    assert row["external_key"] == "INC0010009"


@pytest.mark.asyncio
async def test_resolvido_no_servicenow_volta_como_done(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    connection = await servicenow_connection(engine, org)
    ticket = await servicenow_ticket(engine, org, "sap")
    instance = FakeServiceNow()
    await create_ticket_any(engine, ticket, instance)
    instance.state = {"value": "6", "display_value": "Resolved"}
    from aid_notifier.itsm import sync as dispatch

    await dispatch(
        engine, {"connection_id": connection, "issue_key": "INC0010001"}, instance.transport()
    )
    [row] = await rows(
        engine,
        "select status, external_status from doctor.incident_tickets where id = cast(:t as uuid)",
        t=ticket,
    )
    assert (row["status"], row["external_status"]) == ("done", "Resolved")
    assert instance.reads == ["a" * 32]


@pytest.mark.asyncio
async def test_credenciais_recusadas_pedem_nova_configuracao(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    connection = await servicenow_connection(engine, org)
    instance = FakeServiceNow()
    instance.token_status = 401
    await servicenow.sync(
        engine, {"connection_id": connection, "check": True}, instance.transport()
    )
    [state] = await rows(
        engine,
        "select status, last_error from doctor.itsm_connections where id = cast(:c as uuid)",
        c=connection,
    )
    assert state["status"] == "needs_reauth"
    assert "client id" in state["last_error"]


@pytest.mark.asyncio
async def test_regra_com_canal_servicenow_abre_o_incident(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    await servicenow_connection(engine, org)
    sn_channel = await channel(engine, org, "servicenow")
    await rule(engine, org, {"type": "incident", "min_severity": "critical"}, [sn_channel])
    found = await incident(engine, org, "critical")
    await evaluate(
        engine, {"source": "incident.opened", "incident_id": found}, Fake().senders(), NOON
    )
    [ticket] = await rows(
        engine,
        "select provider, status from doctor.incident_tickets where incident_id = cast(:i as uuid)",
        i=found,
    )
    assert (ticket["provider"], ticket["status"]) == ("servicenow", "creating")


@pytest.mark.asyncio
async def test_grupo_que_nao_existe_falha_o_chamado_com_o_motivo(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    await servicenow_connection(engine, org)
    ticket = await servicenow_ticket(engine, org, "sap")
    instance = FakeServiceNow()
    del instance.groups["SAP Basis"]
    assert await create_ticket_any(engine, ticket, instance) == "failed"
    [row] = await rows(
        engine, "select error from doctor.incident_tickets where id = cast(:t as uuid)", t=ticket
    )
    assert "SAP Basis" in row["error"]
    assert instance.created == []


@pytest.mark.asyncio
async def test_leitura_que_falha_vai_para_o_fim_da_fila(
    engine: AsyncEngine, org: dict[str, str]
) -> None:
    connection = await servicenow_connection(engine, org)
    ticket = await servicenow_ticket(engine, org, "sap")
    instance = FakeServiceNow()
    await create_ticket_any(engine, ticket, instance)
    await run(
        engine,
        "update doctor.incident_tickets set last_synced_at = now() - interval '1 day'"
        " where id = cast(:t as uuid)",
        t=ticket,
    )
    instance.read_status = 404
    await servicenow.sync(engine, {"connection_id": connection}, instance.transport())
    [row] = await rows(
        engine,
        "select status, last_synced_at > now() - interval '1 minute' as touched"
        " from doctor.incident_tickets where id = cast(:t as uuid)",
        t=ticket,
    )
    assert (row["status"], row["touched"]) == ("open", True)
