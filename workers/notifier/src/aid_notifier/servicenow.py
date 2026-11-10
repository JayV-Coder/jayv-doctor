"""ServiceNow (ticket #44): `incident` da Table API por Incidente, status de volta.

A Organização registra um app OAuth na própria instância (client credentials); o client secret
fica no Vault e o token de acesso só na memória desta rodada. O chamado:

- vai para o grupo de atendimento do Sistema responsável do último Diagnóstico, pela regra da
  Organização, ou para o grupo padrão quando é "Indeterminado" ou não tem regra;
- leva impact e urgency pela severidade, o resumo do Diagnóstico com a confiança heurística e
  o link nas work notes, e o id do chamado em `correlation_id`. Antes de criar, procura pelo
  `correlation_id`: entrega repetida ou worker que caiu depois do POST não duplica.

O status volta pela Business Rule do cliente, que chama o nosso webhook com o número do
incident; o webhook só dispara a leitura pela Table API, e a varredura lê o que ficou parado.
"""

import json
import logging
import re
import time
from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Any
from urllib.parse import quote

import httpx
from aid_alerts.network import public_transport
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_notifier.jira import SYNC_BATCH, SYNC_EVERY, SYNC_SECONDS, confidence_text
from aid_notifier.notify import app_url
from aid_notifier.tickets import CLAIM, Claimed, claim, ticket_failed, touch

log = logging.getLogger(__name__)
# Resolvido, Fechado e Cancelado no ServiceNow.
DONE_STATES = {"6", "7", "8"}
SYSTEMS = {"sap": "SAP", "salesforce": "Salesforce", "gcp": "GCP", "other": "Outro"}
DEFAULT_IMPACT = {"impact": 2, "urgency": 2}
SYS_ID = re.compile(r"[0-9a-f]{32}")


class ServiceNowError(Exception):
    """Falha classificada do ServiceNow (para o histórico; nunca a resposta inteira)."""


def summary(incident: Any, diagnosis: Any, recommendations: Sequence[str]) -> str:
    """Texto das work notes: o que o Diagnóstico concluiu e o link. Nunca Eventos brutos."""
    lines = [
        f"Integration AI Doctor · Incidente #{incident.number}",
        f"{incident.integration} · {incident.environment} · severidade {incident.severity}",
    ]
    if diagnosis is None:
        lines.append("Diagnóstico ainda não publicado.")
    else:
        lines += [
            f"Classificação: {diagnosis.classification or '—'}",
            f"Causa provável: {diagnosis.probable_cause or 'inconclusiva'}",
            # Confiança é sempre exibida como heurística (não calibrada).
            f"Confiança heurística: {confidence_text(diagnosis.confidence)}",
            "Sistema responsável: "
            + SYSTEMS.get(diagnosis.responsible_system or "", "Indeterminado"),
        ]
        if recommendations:
            lines.append("Recomendações:")
            lines += [f"- {item}" for item in recommendations]
    lines.append(f"Abrir no Integration AI Doctor: {app_url()}/incidentes/{incident.id}")
    return "\n".join(lines)


def assignment_group(connection: Any, diagnosis: Any) -> str | None:
    """Grupo do Sistema responsável pela regra; sem Sistema (Indeterminado) ou sem regra para
    ele, o grupo padrão."""
    system = diagnosis.responsible_system if diagnosis is not None else None
    groups: Mapping[str, Any] = connection.assignment_groups or {}
    found = groups.get(system) if system else None
    return str(found) if found else connection.default_group


def error_detail(response: httpx.Response) -> str:
    try:
        found = response.json()
    except ValueError:
        return ""
    error = found.get("error") if isinstance(found, dict) else None
    if not isinstance(error, dict):
        return ""
    return "; ".join(str(error[name]) for name in ("message", "detail") if error.get(name))


class ServiceNow:
    """Chamadas à Table API de uma instância, num cliente HTTP só, com o token da rodada."""

    def __init__(
        self, engine: AsyncEngine, connection: Any, transport: httpx.AsyncBaseTransport | None
    ) -> None:
        self.engine = engine
        self.connection = connection
        self.access: str | None = None
        self.expires = 0.0
        self.revoked = False
        # A instância é sempre *.service-now.com (o banco confere); a rede só conecta em
        # endereço público mesmo assim.
        self.client = httpx.AsyncClient(
            transport=transport or public_transport(),
            timeout=httpx.Timeout(15.0),
            follow_redirects=False,
        )

    async def __aenter__(self) -> "ServiceNow":
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        await self.client.aclose()

    async def token(self) -> str:
        if self.revoked:
            raise ServiceNowError("credenciais do ServiceNow recusadas")
        if self.access and self.expires > time.time() + 60:
            return self.access
        async with self.engine.begin() as db:
            await platform_role(db)
            raw = await db.scalar(
                text("select doctor.get_itsm_tokens(cast(:c as uuid))"), {"c": self.connection.id}
            )
        secret = json.loads(raw or "{}")
        try:
            response = await self.client.post(
                f"{self.connection.instance_url}/oauth_token.do",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.connection.client_id,
                    "client_secret": str(secret.get("client_secret", "")),
                },
            )
            found = response.json() if response.status_code == 200 else {}
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceNowError("a instância do ServiceNow não respondeu") from exc
        if response.status_code in (400, 401, 403):
            await self.reauth(
                "O ServiceNow recusou as credenciais: confira o client id e o secret."
            )
            raise ServiceNowError("credenciais do ServiceNow recusadas")
        if not isinstance(found, dict) or "access_token" not in found:
            raise ServiceNowError(f"o ServiceNow respondeu HTTP {response.status_code} no token")
        self.access = str(found["access_token"])
        self.expires = time.time() + float(found.get("expires_in", 1800))
        return self.access

    async def reauth(self, error: str) -> None:
        self.revoked = True
        async with self.engine.begin() as db:
            await platform_role(db)
            await db.execute(
                text(
                    "update doctor.itsm_connections set status = 'needs_reauth', last_error = :e"
                    " where id = cast(:c as uuid)"
                ),
                {"e": error[:500], "c": self.connection.id},
            )

    async def call(
        self, method: str, path: str, params: Mapping[str, str] | None = None, body: Any = None
    ) -> Any:
        token = await self.token()
        try:
            response = await self.client.request(
                method,
                f"{self.connection.instance_url}{path}",
                params=params,
                json=body,
                headers={"authorization": f"Bearer {token}", "accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise ServiceNowError("o ServiceNow não respondeu") from exc
        if response.status_code == 401:
            await self.reauth("O ServiceNow recusou o token: confira o app OAuth da instância.")
            raise ServiceNowError("token do ServiceNow recusado")
        if response.status_code >= 400:
            raise ServiceNowError(
                f"o ServiceNow respondeu HTTP {response.status_code}: {error_detail(response)}"[
                    :300
                ]
            )
        try:
            found = response.json()
        except ValueError as exc:
            raise ServiceNowError("o ServiceNow respondeu algo que não é JSON") from exc
        return found.get("result") if isinstance(found, dict) else None


async def connection_of(db: AsyncConnection, tenant: str) -> Any:
    return (
        await db.execute(
            text(
                "select id::text, tenant_id::text, instance_url, client_id, impact_map,"
                " assignment_groups, default_group, sync_status from doctor.itsm_connections"
                " where tenant_id = cast(:t as uuid) and provider = 'servicenow'"
                " and status = 'active'"
            ),
            {"t": tenant},
        )
    ).first()


async def create_ticket(
    engine: AsyncEngine, ticket: str, transport: httpx.AsyncBaseTransport | None = None
) -> str:
    """Cria o incident reservado; devolve o status final ('skipped' se não era a vez)."""
    claimed = await claim(engine, ticket, "servicenow")
    return await open_incident(engine, claimed, transport) if claimed else "skipped"


async def group_id(servicenow: ServiceNow, group: str) -> str:
    """sys_id do grupo de atendimento: a regra guarda o nome (ou já o sys_id)."""
    if SYS_ID.fullmatch(group):
        return group
    if "^" in group:
        raise ServiceNowError(f"nome de grupo inválido: {group}")
    found = await servicenow.call(
        "GET",
        "/api/now/table/sys_user_group",
        {"sysparm_query": f"name={group}", "sysparm_fields": "sys_id", "sysparm_limit": "1"},
    )
    if not isinstance(found, list) or not found or not isinstance(found[0], dict):
        raise ServiceNowError(f"o grupo {group} não existe no ServiceNow")
    return str(found[0]["sys_id"])


async def open_incident(
    engine: AsyncEngine, claimed: Claimed, transport: httpx.AsyncBaseTransport | None = None
) -> str:
    """O incident do chamado já reservado (procura pelo `correlation_id` antes de criar)."""
    async with engine.begin() as db:
        await platform_role(db)
        connection = await connection_of(db, claimed.tenant_id)
    ticket, incident = claimed.id, claimed.incident
    diagnosis, recommendations = claimed.diagnosis, claimed.recommendations
    if connection is None or incident is None:
        return await ticket_failed(engine, ticket, "ServiceNow não configurado")
    group = assignment_group(connection, diagnosis)
    weights = (connection.impact_map or {}).get(incident.severity) or DEFAULT_IMPACT
    fields: dict[str, Any] = {
        "short_description": f"[Doctor] {incident.title}"[:160],
        "description": f"{incident.title}\n\n{app_url()}/incidentes/{incident.id}",
        "impact": str(weights.get("impact", 2)),
        "urgency": str(weights.get("urgency", 2)),
        "correlation_id": ticket,
        "correlation_display": "Integration AI Doctor",
        "work_notes": summary(incident, diagnosis, recommendations),
    }
    try:
        async with ServiceNow(engine, connection, transport) as servicenow:
            found = await servicenow.call(
                "GET",
                "/api/now/table/incident",
                {
                    "sysparm_query": f"correlation_id={ticket}",
                    "sysparm_fields": "sys_id,number",
                    "sysparm_limit": "1",
                },
            )
            existing = found[0] if isinstance(found, list) and found else None
            if existing is None and group:
                fields["assignment_group"] = await group_id(servicenow, group)
            # Valores crus (impact e urgency 1 a 3, o sys_id do grupo): sem o modo display value,
            # que trocaria os números pelos rótulos da instância.
            created = existing or await servicenow.call(
                "POST", "/api/now/table/incident", {"sysparm_fields": "sys_id,number"}, fields
            )
        number, sys_id = str(created["number"]), str(created["sys_id"])
    except ServiceNowError as exc:
        return await ticket_failed(engine, ticket, str(exc))
    except Exception:
        log.exception("incident %s não abriu", ticket)
        return await ticket_failed(engine, ticket, "falha interna ao abrir o chamado")
    async with engine.begin() as db:
        await platform_role(db)
        await db.execute(
            text(
                "update doctor.incident_tickets set status = 'open', external_key = :k,"
                " external_id = :i, url = :u, assignment_group = :g, error = null,"
                " last_synced_at = now() where id = cast(:t as uuid) and status = 'creating'"
            ),
            {
                "k": number,
                "i": sys_id[:32],
                "u": f"{connection.instance_url}/nav_to.do?uri="
                + quote(f"incident.do?sys_id={sys_id}", safe=""),
                "g": group[:100] if group else None,
                "t": ticket,
            },
        )
    return "open"


async def read_ticket(servicenow: ServiceNow, ticket: Any) -> bool:
    found = await servicenow.call(
        "GET",
        f"/api/now/table/incident/{quote(ticket.external_id, safe='')}",
        {"sysparm_fields": "state,number", "sysparm_display_value": "all"},
    )
    state = found.get("state") if isinstance(found, dict) else None
    value = str(state.get("value", "")) if isinstance(state, dict) else ""
    name = str(state.get("display_value", value))[:80] if isinstance(state, dict) else ""
    async with servicenow.engine.begin() as db:
        await platform_role(db)
        await db.execute(
            text(
                "update doctor.incident_tickets set external_status = :n,"
                " status = case when :done then 'done' else 'open' end, last_synced_at = now()"
                " where id = cast(:t as uuid)"
            ),
            {"n": name, "done": value in DONE_STATES, "t": ticket.id},
        )
    return name != (ticket.external_status or "")


async def sync(
    engine: AsyncEngine,
    payload: Mapping[str, Any],
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """`itsm.sync` do ServiceNow: confere as credenciais (depois da configuração) e lê o status
    do incident do evento ou dos abertos lidos há mais tempo."""
    key = payload.get("issue_key")
    async with engine.begin() as db:
        await platform_role(db)
        tenant = await db.scalar(
            text(
                "select tenant_id::text from doctor.itsm_connections"
                " where id = cast(:c as uuid) and provider = 'servicenow'"
            ),
            {"c": str(payload["connection_id"])},
        )
        connection = await connection_of(db, str(tenant)) if tenant else None
        tickets = (
            list(
                await db.execute(
                    text(
                        "select id::text, external_id, external_key, external_status"
                        " from doctor.incident_tickets where tenant_id = cast(:t as uuid)"
                        " and provider = 'servicenow' and external_id is not null and ("
                        "  (cast(:k as text) is null and status = 'open')"
                        "  or (external_key = cast(:k as text) and status in ('open', 'done')))"
                        " order by last_synced_at nulls first limit :n"
                    ),
                    {"t": tenant, "k": key, "n": SYNC_BATCH},
                )
            )
            if connection
            else []
        )
    if connection is None:
        return 0
    changed = 0
    async with ServiceNow(engine, connection, transport) as servicenow:
        if payload.get("check"):
            try:
                await servicenow.token()
            except ServiceNowError as exc:
                log.warning("credenciais do ServiceNow não conferem: %s", exc)
                return 0
        if not connection.sync_status:
            return 0
        started = time.monotonic()
        for ticket in tickets:
            if servicenow.revoked or time.monotonic() - started > SYNC_SECONDS:
                break
            try:
                changed += await read_ticket(servicenow, ticket)
            except ServiceNowError as exc:
                log.warning("incident %s não sincronizou: %s", ticket.external_key, exc)
                await touch(engine, ticket.id)
    return changed


async def maintain(engine: AsyncEngine, transport: httpx.AsyncBaseTransport | None = None) -> int:
    """Varredura: incidents presos em "criando" e conexões com chamados sem leitura há 15 min
    (a Business Rule do cliente pode não existir ou falhar)."""
    async with engine.begin() as db:
        await platform_role(db)
        stuck = [
            found[0]
            for found in await db.execute(
                text(
                    "select id::text from doctor.incident_tickets where status = 'creating'"
                    " and provider = 'servicenow'"
                    " and coalesce(claimed_at, created_at) < now() - cast(:claim as interval)"
                    " limit 20"
                ),
                {"claim": CLAIM},
            )
        ]
        due = [
            found[0]
            for found in await db.execute(
                text(
                    "select c.id::text from doctor.itsm_connections c"
                    " where c.status = 'active' and c.provider = 'servicenow' and c.sync_status"
                    " and exists (select 1 from doctor.incident_tickets t"
                    "  where t.tenant_id = c.tenant_id and t.provider = 'servicenow'"
                    "  and t.status = 'open' and (t.last_synced_at is null"
                    "  or t.last_synced_at < now() - cast(:every as interval)))"
                    " limit 5"
                ),
                {"every": SYNC_EVERY},
            )
        ]
    done = 0
    for ticket in stuck:
        done += await create_ticket(engine, ticket, transport) == "open"
    for connection in due:
        done += await sync(engine, {"connection_id": connection}, transport)
    return done
