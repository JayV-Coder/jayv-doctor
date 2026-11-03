"""Leitura da Trilha de auditoria dentro de `tenant_tx`: o RLS só mostra a Organização ativa, e
só para Owner e Admin com MFA."""

import base64
import binascii
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from sqlalchemy import text

from aid_api.audit.schemas import AuditEntry, AuditPage, AuditSearch, Category
from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError

# Categoria pelo prefixo da ação (os chips da Tela 18).
CATEGORIES: dict[Category, tuple[str, ...]] = {
    "security": ("membership.", "invitation.", "org.", "auth.", "ingestion_token."),
    "diagnosis": ("diagnosis.",),
    "connectors": ("connector.", "integration.", "vault."),
    "data": ("raw_log.", "knowledge.", "audit.", "report.", "retention."),
    "incidents": ("incident.",),
}
EXPORT_LIMIT = 50_000
ERRORS = {"42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação.")}


def category_of(action: str) -> Category | None:
    for category, prefixes in CATEGORIES.items():
        if action.startswith(prefixes):
            return category
    return None


def bad_cursor() -> ApiError:
    return ApiError(422, "invalid_cursor", "Cursor de paginação inválido.")


def encode_cursor(moment: datetime, ident: int) -> str:
    return base64.urlsafe_b64encode(json.dumps([moment.isoformat(), ident]).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        moment, ident = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(moment), int(ident)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise bad_cursor() from exc


SELECT = (
    "select a.id, a.occurred_at, a.actor_type, a.actor_id::text, a.action,"
    " a.resource_type, a.resource_id, a.before, a.after, host(a.ip) as ip"
    " from doctor.audit_logs a"
)


def select_sql(where: list[str]) -> str:
    # `where` só tem trechos fixos deste módulo; os valores vão como parâmetros.
    clause = " where " + " and ".join(where) if where else ""
    return f"{SELECT}{clause} order by a.occurred_at desc, a.id desc limit :n"


def conditions(query: AuditSearch, actors: list[str]) -> tuple[list[str], dict[str, Any]]:
    where: list[str] = []
    params: dict[str, Any] = {}
    if query.category:
        prefixes = CATEGORIES[query.category]
        where.append("(" + " or ".join(f"a.action like :p{i}" for i in range(len(prefixes))) + ")")
        params.update({f"p{i}": f"{prefix}%" for i, prefix in enumerate(prefixes)})
    if query.q:
        # Escapado, não removido: `role_changed` precisa achar `membership.role_changed`.
        escaped = query.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params["q"] = f"%{escaped}%"
        options = ["a.action ilike :q escape '\\'", "a.resource_id ilike :q escape '\\'"]
        if actors:
            options.append("a.actor_id = any(cast(:actors as uuid[]))")
            params["actors"] = actors
        where.append("(" + " or ".join(options) + ")")
    if query.since:
        where.append("a.occurred_at >= :since")
        params["since"] = query.since
    if query.until:
        where.append("a.occurred_at < :until")
        params["until"] = query.until
    return where, params


class AuditRepository:
    async def _filtered(
        self, connection: Any, query: AuditSearch
    ) -> tuple[dict[str, str], list[str], dict[str, Any]]:
        """Atores (para o rótulo e para o termo bater com o e-mail) e os filtros da consulta."""
        rows = await connection.execute(
            text("select user_id::text, email from doctor.list_audit_actors()")
        )
        members = {row[0]: row[1] for row in rows if row[1]}
        term = (query.q or "").lower()
        actors = [ident for ident, label in members.items() if term and term in label.lower()]
        where, params = conditions(query, actors)
        return members, where, params

    async def search(self, claims: Claims, query: AuditSearch) -> AuditPage:
        async with translated_tx(claims, ERRORS) as connection:
            members, where, params = await self._filtered(connection, query)
            if query.cursor:
                moment, ident = decode_cursor(query.cursor)
                where.append("(a.occurred_at, a.id) < (:cursor_at, :cursor_id)")
                params.update({"cursor_at": moment, "cursor_id": ident})
            rows = list(
                (
                    await connection.execute(
                        text(select_sql(where)), {**params, "n": query.limit + 1}
                    )
                ).mappings()
            )
        page = rows[: query.limit]
        items = [entry(row, members) for row in page]
        last = page[-1] if len(rows) > query.limit else None
        return AuditPage(
            items=items,
            next_cursor=encode_cursor(last["occurred_at"], last["id"]) if last else None,
        )

    async def start_export(self, claims: Claims, query: AuditSearch) -> None:
        """Antes do primeiro byte: confere o acesso (o 403 ainda vira 403) e grava a exportação
        numa transação própria, que não se desfaz se o download for interrompido."""
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(text("select 1 from doctor.list_audit_actors() limit 1"))
            await connection.execute(
                text("select doctor.record_audit_export(cast(:filters as jsonb))"),
                {"filters": query.model_dump_json(include={"category", "since", "until"})},
            )

    async def export(self, claims: Claims, query: AuditSearch) -> AsyncIterator[AuditEntry]:
        """Até EXPORT_LIMIT registros, do mais novo para o mais antigo."""
        async with translated_tx(claims, ERRORS) as connection:
            members, where, params = await self._filtered(connection, query)
            result = await connection.stream(text(select_sql(where)), {**params, "n": EXPORT_LIMIT})
            async for row in result.mappings():
                yield entry(row, members)


def entry(row: Any, members: dict[str, str]) -> AuditEntry:
    actor = row["actor_id"]
    return AuditEntry(
        id=str(row["id"]),
        occurred_at=row["occurred_at"],
        actor_type=row["actor_type"],
        actor_id=actor,
        actor_label=members.get(actor) if actor else None,
        action=row["action"],
        category=category_of(row["action"]),
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        before=row["before"],
        after=row["after"],
        ip=row["ip"],
    )


def get_audit_repository() -> AuditRepository:
    return AuditRepository()
