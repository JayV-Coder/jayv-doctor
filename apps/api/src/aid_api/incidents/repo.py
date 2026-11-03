"""Incidentes dentro de `tenant_tx`: leitura pelo RLS; mudanças e comentários pelas funções do
banco, que conferem Analyst ou acima na tabela e validam a transição de status."""

import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import RowMapping

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.core.pagination import decode_cursor, encode_cursor
from aid_api.incidents.schemas import (
    Comment,
    HistoryEntry,
    IncidentChange,
    IncidentDetail,
    IncidentExecution,
    IncidentPage,
    IncidentSearch,
    IncidentSummary,
    NewComment,
    RuleEvidence,
)

NUMBER = re.compile(r"^(?:inc-?)?0*(\d{1,9})$", re.IGNORECASE)


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Incidente não encontrado.")


ERRORS = {
    "P0002": not_found,
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "DR010": lambda: ApiError(409, "invalid_transition", "Essa mudança de status não é permitida."),
    "DR011": lambda: ApiError(
        422, "invalid_assignee", "O responsável não é membro da Organização."
    ),
    "23514": lambda: ApiError(422, "validation_error", "Os dados enviados são inválidos."),
}

COLUMNS = (
    "n.id::text as id, n.number, n.title, n.category, n.severity, n.status, n.rule_code,"
    " n.rule_version, n.integration_id::text as integration_id, i.name as integration_name,"
    " i.environment, n.first_seen_at, n.last_seen_at, n.execution_count,"
    " n.assignee_id::text as assignee_id, n.resolved_at"
)
FROM = (
    " from doctor.incidents n"
    " join doctor.integrations i on i.tenant_id = n.tenant_id and i.id = n.integration_id"
)
SUMMARY = COLUMNS + FROM


def filters(query: IncidentSearch, reference: str | None) -> tuple[list[str], dict[str, Any]]:
    """Condições comuns à lista e às contagens (sem o status, que é o eixo dos chips)."""
    conditions: list[str] = []
    params: dict[str, Any] = {}
    if query.severity:
        conditions.append("n.severity = any(cast(:severity as text[]))")
        params["severity"] = list(query.severity)
    if query.category:
        conditions.append("n.category = :category")
        params["category"] = query.category
    if query.integration_id:
        conditions.append("n.integration_id = cast(:integration as uuid)")
        params["integration"] = str(query.integration_id)
    if query.environment:
        conditions.append("i.environment = :environment")
        params["environment"] = query.environment
    if query.assignee_id:
        conditions.append("n.assignee_id = cast(:assignee as uuid)")
        params["assignee"] = str(query.assignee_id)
    if query.since:
        conditions.append("n.last_seen_at >= :since")
        params["since"] = query.since
    if query.until:
        conditions.append("n.first_seen_at <= :until")
        params["until"] = query.until
    if query.q:
        term = query.q.strip()
        # Pelas Execuções do Incidente: execution_id, trace_id ou Referência (já em HMAC).
        keys = [
            "x.correlation_keys @> cast(:by_execution as jsonb)",
            "x.correlation_keys @> cast(:by_trace as jsonb)",
        ]
        params["by_execution"] = json.dumps({"execution_id": [term]})
        params["by_trace"] = json.dumps({"trace_id": [term]})
        if reference:
            keys.append("x.correlation_keys @> cast(:by_reference as jsonb)")
            params["by_reference"] = json.dumps({"business_reference": [reference]})
        matches = " or ".join(keys)
        found = [
            "exists (select 1 from doctor.incident_executions ie"  # noqa: S608
            " join doctor.executions x"
            "  on x.tenant_id = ie.tenant_id and x.id = ie.execution_id"
            " where ie.tenant_id = n.tenant_id and ie.incident_id = n.id"
            f" and ({matches}))"
        ]
        # "142" pode ser o INC-0142 ou um pedido curto: vale qualquer um dos dois.
        if (number := NUMBER.match(term)) is not None:
            found.append("n.number = :number")
            params["number"] = int(number.group(1))
        conditions.append(f"({' or '.join(found)})")
    return conditions, params


def where(conditions: list[str]) -> str:
    return f" where {' and '.join(conditions)}" if conditions else ""


class IncidentRepository:
    async def search(
        self, claims: Claims, query: IncidentSearch, reference: str | None
    ) -> IncidentPage:
        common, params = filters(query, reference)
        listed = list(common)
        if query.status:
            listed.append("n.status = any(cast(:status as text[]))")
            params["status"] = list(query.status)
        if query.cursor:
            moment, target = decode_cursor(query.cursor)
            listed.append(
                "(n.last_seen_at, n.id)"
                " < (cast(:cursor_at as timestamptz), cast(:cursor_id as uuid))"
            )
            params["cursor_at"] = moment
            params["cursor_id"] = target
        params["limit"] = query.limit + 1
        async with translated_tx(claims, ERRORS) as connection:
            rows = [
                IncidentSummary.model_validate(dict(row))
                for row in (
                    await connection.execute(
                        text(
                            f"select {SUMMARY}{where(listed)}"
                            " order by n.last_seen_at desc, n.id desc limit :limit"
                        ),
                        params,
                    )
                ).mappings()
            ]
            # Os chips só usam as contagens da primeira página.
            counts = (
                {}
                if query.cursor
                else {
                    row.status: row.total
                    for row in await connection.execute(
                        text(
                            "select n.status, count(*) as total from doctor.incidents n"  # noqa: S608
                            " join doctor.integrations i"
                            "  on i.tenant_id = n.tenant_id and i.id = n.integration_id"
                            f"{where(common)} group by n.status"
                        ),
                        params,
                    )
                }
            )
        items = rows[: query.limit]
        more = len(rows) > query.limit
        return IncidentPage(
            items=items,
            next_cursor=encode_cursor(items[-1].last_seen_at, items[-1].id) if more else None,
            counts=counts,
        )

    async def detail(self, claims: Claims, target: str) -> IncidentDetail:
        async with translated_tx(claims, ERRORS) as connection:
            row: RowMapping | None = (
                (
                    await connection.execute(
                        text(
                            f"select {COLUMNS}, n.resolution_note{FROM}"
                            " where n.id = cast(:n as uuid)"
                        ),
                        {"n": target},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise not_found()
            executions = [
                IncidentExecution.model_validate(dict(item))
                for item in (
                    await connection.execute(
                        text(
                            "select x.id::text as id, x.status, x.first_event_at, x.duration_ms,"
                            " x.event_count, x.correlation_keys"
                            " from doctor.incident_executions ie join doctor.executions x"
                            " on x.tenant_id = ie.tenant_id and x.id = ie.execution_id"
                            " where ie.incident_id = cast(:n as uuid)"
                            " order by x.first_event_at desc limit 50"
                        ),
                        {"n": target},
                    )
                ).mappings()
            ]
            evidence = [
                RuleEvidence.model_validate(dict(item))
                for item in (
                    await connection.execute(
                        text(
                            "select m.execution_id::text as execution_id, m.rule_code,"
                            " m.rule_version, d.category, d.description,"
                            " m.matched_event_ids::text[] as matched_event_ids"
                            " from doctor.incident_executions ie join doctor.rule_matches m"
                            " on m.tenant_id = ie.tenant_id and m.execution_id = ie.execution_id"
                            " join doctor.rule_definitions d"
                            " on d.code = m.rule_code and d.version = m.rule_version"
                            " where ie.incident_id = cast(:n as uuid)"
                            " order by m.created_at desc, m.rule_code limit 50"
                        ),
                        {"n": target},
                    )
                ).mappings()
            ]
            history = [
                HistoryEntry.model_validate(dict(item))
                for item in (
                    await connection.execute(
                        text(
                            "select action, from_value, to_value, note,"
                            " actor_id::text as actor_id, created_at"
                            " from doctor.incident_history where incident_id = cast(:n as uuid)"
                            " order by created_at"
                        ),
                        {"n": target},
                    )
                ).mappings()
            ]
        return IncidentDetail.model_validate(
            {**dict(row), "executions": executions, "evidence": evidence, "history": history}
        )

    async def update(self, claims: Claims, target: str, change: IncidentChange) -> IncidentDetail:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(
                text(
                    "select doctor.update_incident(cast(:n as uuid), :s, :v,"
                    " cast(:a as uuid), :set_a, :note)"
                ),
                {
                    "n": target,
                    "s": change.status,
                    "v": change.severity,
                    "a": str(change.assignee_id) if change.assignee_id else None,
                    "set_a": "assignee_id" in change.model_fields_set,
                    "note": change.resolution_note,
                },
            )
        return await self.detail(claims, target)

    async def comments(self, claims: Claims, target: str) -> list[Comment]:
        async with translated_tx(claims, ERRORS) as connection:
            exists = await connection.scalar(
                text("select 1 from doctor.incidents where id = cast(:n as uuid)"), {"n": target}
            )
            if not exists:
                raise not_found()
            result = await connection.execute(
                text(
                    "select id::text, author_id::text as author_id, body_md,"
                    " mentions::text[] as mentions, created_at from doctor.incident_comments"
                    " where incident_id = cast(:n as uuid) order by created_at"
                ),
                {"n": target},
            )
            return [Comment.model_validate(dict(row)) for row in result.mappings()]

    async def comment(self, claims: Claims, target: str, new: NewComment) -> Comment:
        async with translated_tx(claims, ERRORS) as connection:
            created = await connection.scalar(
                text(
                    "select doctor.add_incident_comment(cast(:n as uuid), :b,"
                    " cast(:m as uuid[]))::text"
                ),
                {"n": target, "b": new.body_md, "m": [str(user) for user in new.mentions]},
            )
            row = (
                (
                    await connection.execute(
                        text(
                            "select id::text, author_id::text as author_id, body_md,"
                            " mentions::text[] as mentions, created_at"
                            " from doctor.incident_comments where id = cast(:c as uuid)"
                        ),
                        {"c": created},
                    )
                )
                .mappings()
                .one()
            )
        return Comment.model_validate(dict(row))


def get_incident_repository() -> IncidentRepository:
    return IncidentRepository()
