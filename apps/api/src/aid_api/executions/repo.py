"""Explorador de Execuções dentro de `tenant_tx`: tudo é leitura, e o RLS limita à Organização
ativa. O download do Log bruto passa por uma função do banco que confere o Papel e audita."""

import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.core.pagination import decode_cursor, encode_cursor
from aid_api.executions.schemas import (
    EventDetail,
    ExecutionDetail,
    ExecutionPage,
    ExecutionSearch,
    ExecutionSummary,
    IncidentRef,
    RawLogRef,
    RuleHit,
    TimelineEvent,
)


def not_found(what: str = "Execução") -> ApiError:
    return ApiError(404, "not_found", f"{what} não encontrado(a).")


ERRORS = {
    "P0002": lambda: not_found("Log bruto"),
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
}

SUMMARY = (
    "x.id::text as id, x.integration_id::text as integration_id, i.name as integration_name,"
    " i.environment, x.status, x.low_confidence, x.first_event_at, x.last_event_at,"
    " x.duration_ms, x.event_count, x.closed_at, x.correlation_keys,"
    " inc.id::text as incident_id, inc.title as incident_title,"
    " inc.severity as incident_severity, inc.status as incident_status"
    " from doctor.executions x"
    " join doctor.integrations i on i.tenant_id = x.tenant_id and i.id = x.integration_id"
    " left join doctor.incident_executions ie"
    "  on ie.tenant_id = x.tenant_id and ie.execution_id = x.id"
    " left join doctor.incidents inc on inc.tenant_id = ie.tenant_id and inc.id = ie.incident_id"
)


def summary(row: RowMapping) -> ExecutionSummary:
    data = dict(row)
    incident = None
    if data["incident_id"]:
        incident = IncidentRef(
            id=data["incident_id"],
            title=data["incident_title"],
            severity=data["incident_severity"],
            status=data["incident_status"],
        )
    for key in ("incident_id", "incident_title", "incident_severity", "incident_status"):
        data.pop(key)
    return ExecutionSummary.model_validate({**data, "incident": incident})


def as_uuid(value: str) -> str | None:
    try:
        return str(UUID(value))
    except ValueError:
        return None


class ExecutionRepository:
    async def search(
        self, claims: Claims, query: ExecutionSearch, reference: str | None
    ) -> ExecutionPage:
        """`reference`: o termo já em HMAC (ou None sem chave configurada)."""
        conditions = ["x.merged_into is null"]
        params: dict[str, Any] = {"limit": query.limit + 1}
        if query.integration_id:
            conditions.append("x.integration_id = cast(:integration as uuid)")
            params["integration"] = str(query.integration_id)
        if query.environment:
            conditions.append("i.environment = :environment")
            params["environment"] = query.environment
        if query.status:
            conditions.append("x.status = :status")
            params["status"] = query.status
        if query.since:
            conditions.append("x.last_event_at >= :since")
            params["since"] = query.since
        if query.until:
            conditions.append("x.first_event_at <= :until")
            params["until"] = query.until
        if query.q:
            term = query.q.strip()
            # Contém, no índice GIN das chaves: execution_id, trace_id ou Referência (HMAC).
            matches = [
                "x.correlation_keys @> cast(:by_execution as jsonb)",
                "x.correlation_keys @> cast(:by_trace as jsonb)",
            ]
            params["by_execution"] = json.dumps({"execution_id": [term]})
            params["by_trace"] = json.dumps({"trace_id": [term]})
            if reference:
                matches.append("x.correlation_keys @> cast(:by_reference as jsonb)")
                params["by_reference"] = json.dumps({"business_reference": [reference]})
            if (target := as_uuid(term)) is not None:
                matches.append("x.id = cast(:target as uuid)")
                params["target"] = target
            conditions.append(f"({' or '.join(matches)})")
        if query.cursor:
            moment, target = decode_cursor(query.cursor)
            conditions.append(
                "(x.first_event_at, x.id)"
                " < (cast(:cursor_at as timestamptz), cast(:cursor_id as uuid))"
            )
            params["cursor_at"] = moment
            params["cursor_id"] = target
        sql = (
            f"select {SUMMARY} where {' and '.join(conditions)}"
            " order by x.first_event_at desc, x.id desc limit :limit"
        )
        async with translated_tx(claims, ERRORS) as connection:
            rows = [
                summary(row) for row in (await connection.execute(text(sql), params)).mappings()
            ]
        more = len(rows) > query.limit
        items = rows[: query.limit]
        return ExecutionPage(
            items=items,
            next_cursor=encode_cursor(items[-1].first_event_at, items[-1].id) if more else None,
        )

    async def detail(self, claims: Claims, target: str) -> ExecutionDetail:
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                (
                    await connection.execute(
                        # Fundida: o detalhe é o da sobrevivente, onde estão os Eventos e as Regras.
                        text(
                            f"select {SUMMARY} where x.id = coalesce("  # noqa: S608
                            " (select merged_into from doctor.executions"
                            "  where id = cast(:x as uuid)),"
                            " cast(:x as uuid))"
                        ),
                        {"x": target},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise not_found()
            base = summary(row)
            events = await self.timeline(
                connection, base.id, base.first_event_at, base.last_event_at
            )
            rules = [
                RuleHit.model_validate(dict(hit))
                for hit in (
                    await connection.execute(
                        text(
                            # Uma por Regra: a da avaliação mais recente, se houver versões.
                            "select distinct on (m.rule_code) m.rule_code, m.rule_version,"
                            " d.category, d.description,"
                            " m.matched_event_ids::text[] as matched_event_ids"
                            " from doctor.rule_matches m join doctor.rule_definitions d"
                            " on d.code = m.rule_code and d.version = m.rule_version"
                            " where m.execution_id = cast(:x as uuid)"
                            " order by m.rule_code, m.created_at desc"
                        ),
                        {"x": base.id},
                    )
                ).mappings()
            ]
        by_event: dict[str, list[str]] = {}
        for hit in rules:
            for event_id in hit.matched_event_ids:
                by_event.setdefault(event_id, []).append(hit.rule_code)
        return ExecutionDetail(
            **base.model_dump(),
            events=[e.model_copy(update={"rule_codes": by_event.get(e.id, [])}) for e in events],
            rules=rules,
        )

    async def timeline(
        self, connection: AsyncConnection, execution: str, first: datetime, last: datetime
    ) -> list[TimelineEvent]:
        # O intervalo da Execução leva o Postgres só às partições dela.
        result = await connection.execute(
            text(
                "select id::text, timestamp, severity, operation, source, error, execution_id,"
                " trace_id, business_reference, correlated_by"
                " from doctor.events where execution_ref = cast(:x as uuid)"
                " and timestamp between :first and :last order by timestamp, id"
            ),
            {"x": execution, "first": first, "last": last},
        )
        return [
            TimelineEvent.model_validate({**dict(row), "rule_codes": []})
            for row in result.mappings()
        ]

    async def event(self, claims: Claims, target: str, at: datetime | None = None) -> EventDetail:
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "select e.id::text, e.execution_ref::text, e.integration_id::text,"
                            " e.timestamp, e.ingested_at, e.schema_version, e.severity,"
                            " e.operation,"
                            " e.source, e.error, e.execution_id, e.trace_id, e.business_context,"
                            " e.attributes, e.sanitization_report, e.correlated_by,"
                            " r.id::text as raw_id, r.source as raw_source, r.expires_at,"
                            " greatest(0, ceil(extract(epoch from (r.expires_at - now()))"
                            "  / 86400))::int"
                            "  as retention_days_left, imp.filename as import_filename"
                            " from doctor.events e"
                            " left join doctor.raw_log_objects r"
                            "  on r.tenant_id = e.tenant_id and r.id = e.raw_log_object_id"
                            " left join doctor.imports imp"
                            "  on imp.tenant_id = r.tenant_id and imp.raw_log_object_id = r.id"
                            " where e.id = cast(:e as uuid)"
                        ),
                        {"e": target},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise not_found("Evento")
        data = dict(row)
        raw = None
        if data["raw_id"]:
            raw = RawLogRef(
                id=data["raw_id"],
                source=data["raw_source"],
                expires_at=data["expires_at"],
                retention_days_left=data["retention_days_left"],
                import_filename=data["import_filename"],
            )
        for key in ("raw_id", "raw_source", "expires_at", "retention_days_left", "import_filename"):
            data.pop(key)
        return EventDetail.model_validate({**data, "raw_log": raw})

    async def raw_log_download(
        self, claims: Claims, target: str, sign: Callable[[str], Awaitable[str]]
    ) -> str:
        """Confere Analyst ou acima, assina a URL e registra a auditoria na mesma transação: se o
        Storage falhar, nada fica registrado como baixado."""
        async with translated_tx(claims, ERRORS) as connection:
            path = await connection.scalar(
                text("select doctor.request_raw_log_download(cast(:r as uuid))"), {"r": target}
            )
            return await sign(str(path))


def get_execution_repository() -> ExecutionRepository:
    return ExecutionRepository()
