"""Jira Service Management (ticket #43): chamado por Incidente, status e comentários de volta.

Os tokens OAuth 2.0 (3LO) ficam no Vault (`doctor.get_itsm_tokens`); o refresh token do
Atlassian gira a cada renovação e volta para o Vault na hora. Tópicos:

- `itsm.ticket`: cria o chamado reservado em `incident_tickets` (uma vez por Incidente);
- `itsm.sync`: registra (ou renova) o webhook do Jira e lê status e comentários dos chamados
  abertos. O webhook do Jira só dispara esta leitura: o que vale é o que a API do Jira devolve;
- `itsm.comment`: comentário do Doctor com o prefixo `#jira` vai para o chamado.

O corpo do chamado leva o resumo do Diagnóstico, a Causa provável com o rótulo de confiança
heurística, as Recomendações e o link para o Incidente. Nunca Eventos brutos.
"""

import json
import logging
import os
import re
import time
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

import httpx
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_notifier.notify import app_url

log = logging.getLogger(__name__)
AUTH_URL = "https://auth.atlassian.com/oauth/token"
API_URL = "https://api.atlassian.com/ex/jira/{cloud}"
LABEL = "integration-ai-doctor"
PREFIX_IN = re.compile(r"^\s*#doctor\b\s*", re.IGNORECASE)
PREFIX_OUT = re.compile(r"^\s*#jira\b\s*", re.IGNORECASE)
WEBHOOK_EVENTS = ["jira:issue_updated", "comment_created"]
SYNC_EVERY = timedelta(minutes=15)


class JiraError(Exception):
    """Falha classificada do Jira (para o histórico; nunca o corpo da resposta inteiro)."""


def public_api_url() -> str:
    return os.environ.get("AID_PUBLIC_API_URL", "http://127.0.0.1:8000").rstrip("/")


def adf(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "version": 1, "content": list(blocks)}


def paragraph(*parts: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": [part for part in parts if part.get("text") != ""]}


def plain(value: str, *, bold: bool = False, link: str | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": value}
    marks = ([{"type": "strong"}] if bold else []) + (
        [{"type": "link", "attrs": {"href": link}}] if link else []
    )
    if marks:
        node["marks"] = marks
    return node


def heading(value: str) -> dict[str, Any]:
    return {"type": "heading", "attrs": {"level": 3}, "content": [plain(value)]}


def bullets(items: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "bulletList",
        "content": [{"type": "listItem", "content": [paragraph(plain(item))]} for item in items],
    }


def adf_text(node: Any) -> str:
    """O texto de um documento ADF (o comentário do Jira), sem a formatação."""
    if isinstance(node, Mapping):
        if node.get("type") == "text":
            return str(node.get("text", ""))
        joined = "".join(adf_text(child) for child in node.get("content", []))
        return joined + ("\n" if node.get("type") == "paragraph" else "")
    if isinstance(node, list):
        return "".join(adf_text(child) for child in node)
    return ""


def confidence_text(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}".replace(".", ",")


def description(incident: Any, diagnosis: Any, recommendations: Sequence[str]) -> dict[str, Any]:
    link = f"{app_url()}/incidentes/{incident.id}"
    blocks = [
        paragraph(
            plain("Incidente ", bold=True),
            plain(f"#{incident.number} · {incident.integration} · {incident.environment}"),
        ),
        paragraph(plain(f"Severidade {incident.severity} · categoria {incident.category}")),
    ]
    if diagnosis is not None:
        blocks += [
            heading("Diagnóstico"),
            paragraph(plain(f"Classificação: {diagnosis.classification or '—'}")),
            paragraph(
                plain("Causa provável: ", bold=True),
                plain(diagnosis.probable_cause or "inconclusiva"),
            ),
            # Confiança é sempre exibida como heurística (não calibrada).
            paragraph(plain(f"Confiança heurística: {confidence_text(diagnosis.confidence)}")),
        ]
        if recommendations:
            blocks += [heading("Recomendações"), bullets(recommendations)]
    else:
        blocks.append(paragraph(plain("Diagnóstico ainda não publicado.")))
    blocks.append(paragraph(plain("Abrir no Integration AI Doctor", link=link)))
    return adf(*blocks)


class Jira:
    """Chamadas ao Jira de uma conexão, com a renovação do token quando vence."""

    def __init__(
        self, engine: AsyncEngine, connection: Any, transport: httpx.AsyncBaseTransport | None
    ) -> None:
        self.engine = engine
        self.connection = connection
        self.transport = transport
        self.tokens: dict[str, Any] | None = None

    async def token(self, client: httpx.AsyncClient) -> str:
        if self.tokens is None:
            async with self.engine.begin() as db:
                await platform_role(db)
                raw = await db.scalar(
                    text("select doctor.get_itsm_tokens(cast(:c as uuid))"),
                    {"c": self.connection.id},
                )
            self.tokens = json.loads(raw or "{}")
        if float(self.tokens.get("expires_at", 0)) > time.time() + 60:
            return str(self.tokens["access_token"])
        response = await client.post(
            AUTH_URL,
            json={
                "grant_type": "refresh_token",
                "client_id": os.environ.get("AID_ATLASSIAN_CLIENT_ID", ""),
                "client_secret": os.environ.get("AID_ATLASSIAN_CLIENT_SECRET", ""),
                "refresh_token": self.tokens.get("refresh_token", ""),
            },
        )
        if response.status_code in (400, 401, 403):
            await self.mark(
                "needs_reauth", "O Atlassian recusou a renovação: conecte o Jira de novo."
            )
            raise JiraError("autorização do Jira vencida")
        if response.status_code != 200:
            raise JiraError(f"o Atlassian respondeu HTTP {response.status_code} na renovação")
        found = response.json()
        self.tokens = {
            "access_token": found["access_token"],
            "refresh_token": found.get("refresh_token", self.tokens.get("refresh_token")),
            "expires_at": time.time() + float(found.get("expires_in", 3600)),
        }
        async with self.engine.begin() as db:
            await platform_role(db)
            await db.execute(
                text("select doctor.put_itsm_tokens(cast(:c as uuid), :t)"),
                {"c": self.connection.id, "t": json.dumps(self.tokens)},
            )
        return str(self.tokens["access_token"])

    async def mark(self, status: str, error: str) -> None:
        async with self.engine.begin() as db:
            await platform_role(db)
            await db.execute(
                text(
                    "update doctor.itsm_connections set status = :s, last_error = :e"
                    " where id = cast(:c as uuid)"
                ),
                {"s": status, "e": error[:500], "c": self.connection.id},
            )

    async def call(self, method: str, path: str, body: Any = None) -> Any:
        async with httpx.AsyncClient(
            transport=self.transport, timeout=httpx.Timeout(15.0), follow_redirects=False
        ) as client:
            token = await self.token(client)
            url = API_URL.format(cloud=self.connection.cloud_id) + path
            try:
                response = await client.request(
                    method,
                    url,
                    json=body,
                    headers={"authorization": f"Bearer {token}", "accept": "application/json"},
                )
            except httpx.HTTPError as exc:
                raise JiraError("o Jira não respondeu") from exc
        if response.status_code == 401:
            await self.mark("needs_reauth", "O Jira recusou o token: conecte o Jira de novo.")
            raise JiraError("token do Jira recusado")
        if response.status_code >= 400:
            # A mensagem do Jira diz o campo (projeto, tipo, prioridade): curta, para o histórico.
            detail = ""
            try:
                errors = response.json()
                detail = "; ".join(
                    [*errors.get("errorMessages", []), *map(str, errors.get("errors", {}).values())]
                )
            except ValueError:
                detail = ""
            raise JiraError(f"o Jira respondeu HTTP {response.status_code}: {detail}"[:300])
        return response.json() if response.content else None


async def connection_of(db: AsyncConnection, tenant: str) -> Any:
    return (
        await db.execute(
            text(
                "select id::text, tenant_id::text, cloud_id, site_url, project_key, issue_type,"
                " priority_map, custom_fields, sync_status, jira_webhook_id,"
                " jira_webhook_expires_at from doctor.itsm_connections"
                " where tenant_id = cast(:t as uuid) and provider = 'jira' and status = 'active'"
            ),
            {"t": tenant},
        )
    ).first()


async def create_ticket(
    engine: AsyncEngine, ticket: str, transport: httpx.AsyncBaseTransport | None = None
) -> str:
    """Cria o chamado reservado; devolve o status final ('skipped' se não era a vez)."""
    async with engine.begin() as db:
        await platform_role(db)
        row = (
            await db.execute(
                text(
                    "select t.id::text, t.tenant_id::text, t.incident_id::text from"
                    " doctor.incident_tickets t where t.id = cast(:t as uuid)"
                    " and t.status = 'creating' for update skip locked"
                ),
                {"t": ticket},
            )
        ).first()
        if row is None:
            return "skipped"
        connection = await connection_of(db, row.tenant_id)
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
                    "select id::text, classification, probable_cause, confidence::float"
                    " from doctor.diagnoses where incident_id = cast(:i as uuid)"
                    " and status in ('published', 'inconclusive', 'failed_llm')"
                    " order by version desc limit 1"
                ),
                {"i": row.incident_id},
            )
        ).first()
        recommendations = [
            found[0]
            for found in await db.execute(
                text(
                    "select text from doctor.diagnosis_recommendations"
                    " where diagnosis_id = cast(:d as uuid) order by rank"
                ),
                {"d": diagnosis.id if diagnosis else "00000000-0000-0000-0000-000000000000"},
            )
        ]
    if connection is None or incident is None:
        return await ticket_failed(engine, ticket, "Jira não configurado")
    fields: dict[str, Any] = {
        "project": {"key": connection.project_key},
        "issuetype": {"name": connection.issue_type or "Task"},
        "summary": f"[Doctor] {incident.title}"[:250],
        "description": description(incident, diagnosis, recommendations),
        "labels": [LABEL],
        **{str(key): value for key, value in (connection.custom_fields or {}).items()},
    }
    priority = (connection.priority_map or {}).get(incident.severity)
    if priority:
        fields["priority"] = {"name": str(priority)}
    try:
        created = await Jira(engine, connection, transport).call(
            "POST", "/rest/api/3/issue", {"fields": fields}
        )
    except JiraError as exc:
        return await ticket_failed(engine, ticket, str(exc))
    key = str(created["key"])
    async with engine.begin() as db:
        await platform_role(db)
        await db.execute(
            text(
                "update doctor.incident_tickets set status = 'open', external_key = :k,"
                " external_id = :i, url = :u, error = null, last_synced_at = now(),"
                " comments_synced_at = now() where id = cast(:t as uuid)"
            ),
            {
                "k": key,
                "i": str(created.get("id", ""))[:32],
                "u": f"{connection.site_url}/browse/{key}",
                "t": ticket,
            },
        )
    return "open"


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


async def register_webhook(jira: Jira, token: str) -> None:
    """Webhook dinâmico do Jira só para os chamados do Doctor (pelo rótulo)."""
    found = await jira.call(
        "POST",
        "/rest/api/3/webhook",
        {
            "url": f"{public_api_url()}/api/v1/itsm/jira/hooks/{token}",
            "webhooks": [
                {
                    "events": WEBHOOK_EVENTS,
                    "jqlFilter": f"labels = {LABEL}",
                }
            ],
        },
    )
    created = (found or {}).get("webhookRegistrationResult", [{}])[0].get("createdWebhookId")
    async with jira.engine.begin() as db:
        await platform_role(db)
        await db.execute(
            text(
                "update doctor.itsm_connections set jira_webhook_id = :w,"
                " jira_webhook_expires_at = now() + interval '30 days' where id = cast(:c as uuid)"
            ),
            {"w": created, "c": jira.connection.id},
        )


async def refresh_webhook(jira: Jira) -> None:
    found = await jira.call(
        "PUT", "/rest/api/3/webhook/refresh", {"webhookIds": [jira.connection.jira_webhook_id]}
    )
    expires = (found or {}).get("expirationDate")
    async with jira.engine.begin() as db:
        await platform_role(db)
        await db.execute(
            text(
                "update doctor.itsm_connections set jira_webhook_expires_at ="
                " coalesce(cast(:e as timestamptz), now() + interval '30 days')"
                " where id = cast(:c as uuid)"
            ),
            {"e": expires, "c": jira.connection.id},
        )


async def sync(
    engine: AsyncEngine,
    payload: Mapping[str, Any],
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """`itsm.sync`: (re)registra o webhook se pedido e lê status e comentários dos chamados
    abertos da conexão. Devolve quantos chamados mudaram."""
    async with engine.begin() as db:
        await platform_role(db)
        tenant = await db.scalar(
            text("select tenant_id::text from doctor.itsm_connections where id = cast(:c as uuid)"),
            {"c": str(payload["connection_id"])},
        )
        connection = await connection_of(db, str(tenant)) if tenant else None
        tickets = (
            list(
                await db.execute(
                    text(
                        "select id::text, incident_id::text, external_key, external_status,"
                        " comments_synced_at from doctor.incident_tickets"
                        " where tenant_id = cast(:t as uuid) and status in ('open', 'done')"
                        " and external_key is not null order by last_synced_at nulls first limit 50"
                    ),
                    {"t": tenant},
                )
            )
            if connection
            else []
        )
    if connection is None:
        return 0
    jira = Jira(engine, connection, transport)
    if payload.get("register") and payload.get("hook_token"):
        try:
            await register_webhook(jira, str(payload["hook_token"]))
        except JiraError as exc:
            await jira.mark("active", f"Webhook do Jira não registrado: {exc}")
    if not connection.sync_status:
        return 0
    changed = 0
    for ticket in tickets:
        try:
            issue = await jira.call(
                "GET", f"/rest/api/3/issue/{ticket.external_key}?fields=status,comment"
            )
        except JiraError as exc:
            log.warning("chamado %s não sincronizou: %s", ticket.external_key, exc)
            continue
        fields = (issue or {}).get("fields", {})
        status = fields.get("status") or {}
        name = str(status.get("name", ""))[:80]
        done = (status.get("statusCategory") or {}).get("key") == "done"
        comments = [
            item
            for item in (fields.get("comment") or {}).get("comments", [])
            if PREFIX_IN.match(adf_text(item.get("body")))
        ]
        async with engine.begin() as db:
            await platform_role(db)
            await db.execute(
                text(
                    "update doctor.incident_tickets set external_status = :n,"
                    " status = case when :done then 'done' else 'open' end,"
                    " last_synced_at = now(), comments_synced_at = now()"
                    " where id = cast(:t as uuid)"
                ),
                {"n": name, "done": done, "t": ticket.id},
            )
            for item in comments:
                body = PREFIX_IN.sub("", adf_text(item.get("body"))).strip()[:3900]
                if not body:
                    continue
                await db.execute(
                    text(
                        "insert into doctor.incident_comments (tenant_id, incident_id, body_md,"
                        " external_author, external_id) values (cast(:t as uuid),"
                        " cast(:i as uuid), :b, :a, :x)"
                        " on conflict (tenant_id, incident_id, external_id)"
                        " where external_id is not null do nothing"
                    ),
                    {
                        "t": tenant,
                        "i": ticket.incident_id,
                        "b": f"Do Jira ({ticket.external_key}): {body}",
                        "a": str((item.get("author") or {}).get("displayName", "Jira"))[:120],
                        "x": f"jira:{item.get('id')}",
                    },
                )
        changed += name != (ticket.external_status or "")
    return changed


async def post_comment(
    engine: AsyncEngine,
    payload: Mapping[str, Any],
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """`itsm.comment`: o comentário `#jira …` do Doctor vai para o chamado do Incidente."""
    async with engine.begin() as db:
        await platform_role(db)
        row = (
            await db.execute(
                text(
                    "select c.tenant_id::text, c.body_md, t.external_key,"
                    " doctor.comment_author_name(c.id) as author"
                    " from doctor.incident_comments c join doctor.incident_tickets t"
                    " on t.tenant_id = c.tenant_id and t.incident_id = c.incident_id"
                    " where c.id = cast(:c as uuid) and t.external_key is not null"
                ),
                {"c": str(payload["comment_id"])},
            )
        ).first()
        connection = await connection_of(db, row.tenant_id) if row else None
    if row is None or connection is None:
        return False
    body = PREFIX_OUT.sub("", row.body_md).strip()
    try:
        await Jira(engine, connection, transport).call(
            "POST",
            f"/rest/api/3/issue/{row.external_key}/comment",
            {"body": adf(paragraph(plain(f"[Doctor] {row.author}: ", bold=True), plain(body)))},
        )
    except JiraError as exc:
        log.warning("comentário não foi ao Jira: %s", exc)
        return False
    return True


async def maintain(engine: AsyncEngine, transport: httpx.AsyncBaseTransport | None = None) -> int:
    """Varredura: renova webhooks do Jira perto de vencer e sincroniza conexões com chamados
    sem leitura há 15 min (o webhook do Jira pode falhar ou atrasar)."""
    async with engine.begin() as db:
        await platform_role(db)
        due = list(
            await db.execute(
                text(
                    "select c.id::text, c.tenant_id::text,"
                    " c.jira_webhook_id is not null and c.jira_webhook_expires_at"
                    "  < now() + interval '5 days' as renew"
                    " from doctor.itsm_connections c where c.status = 'active' and ("
                    " (c.jira_webhook_id is not null"
                    "  and c.jira_webhook_expires_at < now() + interval '5 days')"
                    " or exists (select 1 from doctor.incident_tickets t"
                    "  where t.tenant_id = c.tenant_id and t.status = 'open'"
                    "  and (t.last_synced_at is null or t.last_synced_at < now() - :every)))"
                    " limit 20"
                ),
                {"every": SYNC_EVERY},
            )
        )
    done = 0
    for row in due:
        if row.renew:
            async with engine.begin() as db:
                await platform_role(db)
                connection = await connection_of(db, row.tenant_id)
            if connection is not None:
                try:
                    await refresh_webhook(Jira(engine, connection, transport))
                except JiraError as exc:
                    log.warning("webhook do Jira não renovou: %s", exc)
        done += await sync(engine, {"connection_id": row.id}, transport)
    return done
