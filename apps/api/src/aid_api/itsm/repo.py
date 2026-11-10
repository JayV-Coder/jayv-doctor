"""Jira dentro de `tenant_tx`. A API troca o código do OAuth pelos tokens e os grava no Vault
pela função do banco, mas não os lê: quem usa os tokens é o worker `notifier` (ADR-0017)."""

import hashlib
import json
import os
import re
import secrets
import time
from urllib.parse import urlencode

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_api.core.auth import Claims
from aid_api.core.db import anonymous_tx, translated_tx
from aid_api.core.errors import ApiError
from aid_api.itsm.schemas import Authorization, JiraConfig, JiraConnection, Ticket

AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
TOKEN_URL = "https://auth.atlassian.com/oauth/token"  # noqa: S105 - endereço, não segredo
RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
SCOPES = "read:jira-work write:jira-work manage:jira-webhook read:jira-user offline_access"
CUSTOM_FIELD = re.compile(r"^customfield_[0-9]{1,10}$")
CONNECTION_COLUMNS = (
    "status, sites, cloud_id, site_url, project_key, issue_type, priority_map, custom_fields,"
    " sync_status, jira_webhook_expires_at, last_error"
)
TICKET_COLUMNS = (
    "id::text, provider, status, external_key, url, external_status, error, created_at,"
    " last_synced_at"
)


def hashed(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


ERRORS = {
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "P0002": lambda: ApiError(404, "not_found", "Incidente ou conexão do Jira não encontrada."),
    "DR080": lambda: ApiError(409, "jira_not_configured", "Conecte e configure o Jira antes."),
    "DR081": lambda: ApiError(
        400, "invalid_state", "A autorização do Jira venceu ou não é desta sessão: tente de novo."
    ),
    "DR082": lambda: ApiError(422, "invalid_site", "O site escolhido não está na autorização."),
}


def client_credentials() -> tuple[str, str, str]:
    client_id = os.environ.get("AID_ATLASSIAN_CLIENT_ID", "")
    secret = os.environ.get("AID_ATLASSIAN_CLIENT_SECRET", "")
    redirect = os.environ.get("AID_ATLASSIAN_REDIRECT_URI", "")
    if not client_id or not secret or not redirect:
        raise ApiError(503, "jira_unavailable", "O app do Jira não está configurado na plataforma.")
    return client_id, secret, redirect


class ItsmRepository:
    def __init__(
        self, engine: AsyncEngine | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.engine = engine
        self.transport = transport

    async def connection(self, claims: Claims) -> JiraConnection | None:
        async with translated_tx(claims, ERRORS, self.engine) as db:
            row = (
                (
                    await db.execute(
                        text(
                            f"select {CONNECTION_COLUMNS} from doctor.itsm_connections"  # noqa: S608
                            " where provider = 'jira'"
                        )
                    )
                )
                .mappings()
                .first()
            )
            return JiraConnection.model_validate(dict(row)) if row else None

    async def authorize(self, claims: Claims) -> Authorization:
        client_id, _, redirect = client_credentials()
        state = secrets.token_urlsafe(32)
        async with translated_tx(claims, ERRORS, self.engine) as db:
            await db.execute(text("select doctor.start_itsm_oauth(:s)"), {"s": hashed(state)})
        query = urlencode(
            {
                "audience": "api.atlassian.com",
                "client_id": client_id,
                "scope": SCOPES,
                "redirect_uri": redirect,
                "state": state,
                "response_type": "code",
                "prompt": "consent",
            }
        )
        return Authorization(url=f"{AUTHORIZE_URL}?{query}")

    async def callback(self, claims: Claims, code: str, state: str) -> JiraConnection | None:
        client_id, secret, redirect = client_credentials()
        async with httpx.AsyncClient(
            transport=self.transport, timeout=httpx.Timeout(15.0), follow_redirects=False
        ) as client:
            try:
                exchanged = await client.post(
                    TOKEN_URL,
                    json={
                        "grant_type": "authorization_code",
                        "client_id": client_id,
                        "client_secret": secret,
                        "code": code,
                        "redirect_uri": redirect,
                    },
                )
                if exchanged.status_code != 200:
                    raise ApiError(400, "jira_denied", "O Atlassian recusou a autorização.")
                tokens = exchanged.json()
                found = await client.get(
                    RESOURCES_URL, headers={"authorization": f"Bearer {tokens['access_token']}"}
                )
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise ApiError(502, "jira_unreachable", "O Atlassian não respondeu.") from exc
        sites = [
            {"id": str(site["id"]), "name": str(site.get("name", "")), "url": str(site["url"])}
            for site in (found.json() if found.status_code == 200 else [])
            if isinstance(site, dict) and str(site.get("url", "")).startswith("https://")
        ]
        stored = json.dumps(
            {
                "access_token": tokens["access_token"],
                "refresh_token": tokens.get("refresh_token", ""),
                "expires_at": time.time() + float(tokens.get("expires_in", 3600)),
            }
        )
        async with translated_tx(claims, ERRORS, self.engine) as db:
            await db.execute(
                text("select doctor.finish_itsm_oauth(:s, :t, cast(:sites as jsonb))"),
                {"s": hashed(state), "t": stored, "sites": json.dumps(sites)},
            )
        return await self.connection(claims)

    async def configure(self, claims: Claims, config: JiraConfig) -> JiraConnection | None:
        if not all(CUSTOM_FIELD.match(name) for name in config.custom_fields):
            raise ApiError(
                422, "validation_error", "Campos customizados: ids customfield_<número>."
            )
        async with translated_tx(claims, ERRORS, self.engine) as db:
            await db.execute(
                text(
                    "select doctor.configure_jira(:c, :p, :i, cast(:m as jsonb),"
                    " cast(:f as jsonb), :s, :h)"
                ),
                {
                    "c": config.cloud_id,
                    "p": config.project_key,
                    "i": config.issue_type.strip(),
                    "m": json.dumps(config.priority_map),
                    "f": json.dumps(config.custom_fields),
                    "s": config.sync_status,
                    # Endereço novo do webhook do Jira a cada configuração.
                    "h": secrets.token_urlsafe(32),
                },
            )
        return await self.connection(claims)

    async def disconnect(self, claims: Claims) -> None:
        async with translated_tx(claims, ERRORS, self.engine) as db:
            await db.execute(text("select doctor.disconnect_jira()"))

    async def tickets(self, claims: Claims, incident: str) -> list[Ticket]:
        async with translated_tx(claims, ERRORS, self.engine) as db:
            visible = await db.scalar(
                text("select 1 from doctor.incidents where id = cast(:i as uuid)"), {"i": incident}
            )
            if visible is None:
                raise ApiError(404, "not_found", "Incidente não encontrado.")
            result = await db.execute(
                text(
                    f"select {TICKET_COLUMNS} from doctor.incident_tickets"  # noqa: S608
                    " where incident_id = cast(:i as uuid) order by created_at"
                ),
                {"i": incident},
            )
            return [Ticket.model_validate(dict(row)) for row in result.mappings()]

    async def request(self, claims: Claims, incident: str) -> list[Ticket]:
        async with translated_tx(claims, ERRORS, self.engine) as db:
            await db.execute(
                text("select doctor.request_ticket(cast(:i as uuid))"), {"i": incident}
            )
        return await self.tickets(claims, incident)

    async def hook(self, token: str) -> None:
        async with anonymous_tx({}) as db:
            await db.execute(text("select doctor.jira_hook(:h)"), {"h": hashed(token)})


def get_itsm_repository() -> ItsmRepository:
    return ItsmRepository()
