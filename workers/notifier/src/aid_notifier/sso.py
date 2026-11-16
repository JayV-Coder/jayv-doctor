"""SSO corporativo (ticket #48, ADR-0021): tarefas da plataforma, fora do alcance da
Organização.

- `sso.domain`: confere o TXT `_aid-sso.<domínio>` (`aid-sso=<token>`) por DNS sobre HTTPS e
  marca o domínio como verificado; depois, pede a sincronização do provedor.
- `sso.sync`: registra (ou atualiza, ou remove) o provedor SAML no Supabase Auth do projeto pela
  Management API, com os domínios verificados e o atributo `groups`. Sem `SUPABASE_ACCESS_TOKEN`
  e `SUPABASE_PROJECT_REF`, a conexão fica `pending_platform`: o projeto é compartilhado com o
  jayv-coder (ADR-0009), e a operação decide quando ligar.
"""

import logging
import os
from collections.abc import Mapping
from typing import Any

import httpx
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)
DOH_URL = "https://dns.google/resolve"
MANAGEMENT_URL = "https://api.supabase.com/v1/projects/{ref}/config/auth/sso/providers"
PENDING = "Aguardando a operação registrar o provedor no Supabase Auth (docs/operations/sso.md)."
TIMEOUT = httpx.Timeout(15.0)


class DnsUnavailableError(RuntimeError):
    """O DNS público não respondeu: não dá para dizer que o TXT não existe."""


async def txt_records(name: str, transport: httpx.AsyncBaseTransport | None = None) -> list[str]:
    try:
        async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT) as client:
            response = await client.get(DOH_URL, params={"name": name, "type": "TXT"})
    except httpx.HTTPError as exc:
        raise DnsUnavailableError(name) from exc
    if response.status_code != 200:
        raise DnsUnavailableError(f"{name}: HTTP {response.status_code}")
    answers = response.json().get("Answer") or []
    return [str(item.get("data", "")).strip('"') for item in answers if isinstance(item, dict)]


async def verify_domain(
    engine: AsyncEngine,
    payload: Mapping[str, Any],
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """Marca o domínio quando o TXT está lá. Nunca desfaz: DNS fora do ar (a mensagem volta para
    a fila) ou TXT removido depois da prova não desligam o SSO de ninguém."""
    async with engine.begin() as db:
        await platform_role(db)
        row = (
            await db.execute(
                text(
                    "select d.id::text, d.tenant_id::text, d.domain, d.token"
                    " from doctor.sso_domains d where d.id = cast(:d as uuid)"
                ),
                {"d": str(payload["domain_id"])},
            )
        ).first()
    if row is None:
        return False
    found = await txt_records(f"_aid-sso.{row.domain}", transport)
    if f"aid-sso={row.token}" not in found:
        return False
    async with engine.begin() as db:
        await platform_role(db)
        # Falso: outra Organização provou o mesmo domínio antes.
        verified = bool(
            await db.scalar(text("select doctor.mark_sso_domain(cast(:d as uuid))"), {"d": row.id})
        )
        if verified:
            # O provedor no Supabase Auth passa a conhecer o domínio.
            await db.execute(
                text(
                    "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                    " select c.tenant_id, 'sso.sync', jsonb_build_object('connection_id', c.id)"
                    " from doctor.sso_connections c where c.tenant_id = cast(:t as uuid)"
                ),
                {"t": row.tenant_id},
            )
    return verified


async def mark(
    engine: AsyncEngine, connection: str, provider: str | None, status: str, error: str | None
) -> bool:
    """Falso quando a conexão já não existe (o Owner desligou o SSO no meio do registro)."""
    async with engine.begin() as db:
        await platform_role(db)
        return bool(
            await db.scalar(
                text("select doctor.set_sso_provider(cast(:c as uuid), cast(:p as uuid), :s, :e)"),
                {"c": connection, "p": provider, "s": status, "e": error},
            )
        )


async def remove_provider(
    client: httpx.AsyncClient, base: str, headers: dict[str, str], provider: str
) -> None:
    """Só conta como removido quando o Supabase confirma (ou diz que já não existe): senão a
    mensagem volta para a fila, e o provedor não fica aceitando login do domínio."""
    response = await client.delete(f"{base}/{provider}", headers=headers)
    if response.status_code != 404:
        response.raise_for_status()


def provider_of_domains(listing: Any, domains: list[str]) -> str | None:
    """O provedor que já tem um dos domínios (verificados, então nossos): uma reentrega depois
    de um POST que deu certo atualiza esse, em vez de criar outro e esbarrar no domínio."""
    items = listing.get("items") if isinstance(listing, dict) else listing
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        owned = {
            entry.get("domain") if isinstance(entry, dict) else entry
            for entry in item.get("domains") or []
        }
        if owned & set(domains) and isinstance(item.get("id"), str):
            return str(item["id"])
    return None


async def sync(
    engine: AsyncEngine,
    payload: Mapping[str, Any],
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Devolve o status final da conexão (ou `removed`)."""
    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    ref = os.environ.get("SUPABASE_PROJECT_REF", "")
    base = MANAGEMENT_URL.format(ref=ref)
    headers = {"authorization": f"Bearer {token}"}
    removed = payload.get("remove_provider")
    if removed:
        if token and ref:
            async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT) as client:
                await remove_provider(client, base, headers, str(removed))
        return "removed"
    async with engine.begin() as db:
        await platform_role(db)
        row = (
            await db.execute(
                text(
                    "select c.id::text, c.metadata_url, c.provider_id::text,"
                    " coalesce(array_agg(d.domain order by d.domain)"
                    "  filter (where d.verified_at is not null), '{}') as domains"
                    " from doctor.sso_connections c"
                    " left join doctor.sso_domains d on d.tenant_id = c.tenant_id"
                    " where c.id = cast(:c as uuid) group by c.id"
                ),
                {"c": str(payload["connection_id"])},
            )
        ).first()
    if row is None:
        return "missing"
    if not row.domains:
        await mark(engine, row.id, None, "pending_platform", "Verifique um domínio pelo DNS.")
        return "pending_platform"
    if not token or not ref:
        await mark(engine, row.id, None, "pending_platform", PENDING)
        return "pending_platform"
    body = {
        "metadata_url": row.metadata_url,
        "domains": list(row.domains),
        "attribute_mapping": {"keys": {"groups": {"name": "groups", "array": True}}},
    }
    try:
        async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT) as client:
            known = row.provider_id
            if not known:
                listing = await client.get(base, headers=headers)
                if listing.status_code == 200:
                    known = provider_of_domains(listing.json(), list(row.domains))
            if known:
                response = await client.put(f"{base}/{known}", json=body, headers=headers)
            else:
                response = await client.post(base, json={"type": "saml", **body}, headers=headers)
    except httpx.HTTPError:
        await mark(engine, row.id, None, "error", "A Management API do Supabase não respondeu.")
        return "error"
    if response.status_code >= 400:
        detail = response.text[:200]
        await mark(
            engine,
            row.id,
            None,
            "error",
            f"Supabase recusou o provedor: HTTP {response.status_code} {detail}",
        )
        return "error"
    provider = str(response.json().get("id") or known or "") or None
    if await mark(engine, row.id, provider, "active", None):
        return "active"
    # O Owner desligou o SSO enquanto o provedor era registrado: ninguém mais o removeria.
    if provider:
        async with httpx.AsyncClient(transport=transport, timeout=TIMEOUT) as client:
            await remove_provider(client, base, headers, provider)
    return "removed"
