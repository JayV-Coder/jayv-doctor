"""Geração do Relatório técnico (ticket #32), pela mensagem `report.requested`. A leitura é feita
em nome da Organização (RLS valendo, `tenant_role`); o arquivo vai para o bucket `doctor-reports`
em `{tenant_id}/{report_id}.{formato}` e a linha fica `ready` com o tamanho e o hash."""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from aid_db import platform_role, tenant_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_diagnosis_worker.report_render import Format, ReportData, render
from aid_diagnosis_worker.retention import REPORTS, Storage

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
# A geração leva segundos; a posse curta deixa a reentrega retomar logo depois de uma queda.
LEASE = timedelta(minutes=2)
TIMELINE_LIMIT = 500
EXCERPT_CHARS = 600


async def claim(engine: AsyncEngine, report_id: str) -> Any:
    async with engine.begin() as connection:
        await platform_role(connection)
        return (
            await connection.execute(
                text(
                    "update doctor.reports set status = 'running', attempts = attempts + 1"
                    " where id = cast(:r as uuid) and (status = 'queued' or status = 'running'"
                    " and updated_at < now() - make_interval(secs => :lease))"
                    " returning id::text, tenant_id::text, incident_id::text,"
                    " diagnosis_id::text, format, include_timeline, include_event_excerpts,"
                    " attempts"
                ),
                {"r": report_id, "lease": LEASE.total_seconds()},
            )
        ).first()


async def rows(connection: AsyncConnection, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in (await connection.execute(text(sql), params)).mappings()]


async def excerpt(connection: AsyncConnection, event: str, at: datetime) -> str | None:
    """Trecho do Evento (já sanitizado na ingestão; o template sanitiza de novo). Fora a
    Referência e o contexto de negócio."""
    found = (
        await connection.execute(
            text(
                "select jsonb_strip_nulls(jsonb_build_object('operation', operation,"
                " 'severity', severity, 'error', error, 'attributes', attributes))::text"
                " from doctor.events where id = cast(:e as uuid) and timestamp = :at"
            ),
            {"e": event, "at": at},
        )
    ).scalar()
    return None if found is None else str(found)[:EXCERPT_CHARS]


async def load(engine: AsyncEngine, report: Any) -> ReportData:
    async with engine.begin() as connection:
        await platform_role(connection)
        organization = await connection.scalar(
            text("select name from public.organizations where id = cast(:t as uuid)"),
            {"t": report.tenant_id},
        )
        reviews = (
            await rows(
                connection,
                "select verdict, reviewer, comment, created_at"
                " from doctor.report_reviews(cast(:t as uuid), cast(:d as uuid))",
                t=report.tenant_id,
                d=report.diagnosis_id,
            )
            if report.diagnosis_id
            else []
        )
    async with engine.begin() as connection:
        await tenant_role(connection, report.tenant_id)
        incident = (
            await rows(
                connection,
                "select i.number, i.title, i.category, i.severity, i.status, i.first_seen_at,"
                " i.last_seen_at, i.execution_count, i.rule_code, i.rule_version,"
                " g.name as integration, g.environment"
                " from doctor.incidents i join doctor.integrations g"
                " on g.tenant_id = i.tenant_id and g.id = i.integration_id"
                " where i.id = cast(:i as uuid)",
                i=report.incident_id,
            )
        )[0]
        diagnosis, hypotheses, evidence, recommendations = None, [], [], []
        if report.diagnosis_id:
            found = await rows(
                connection,
                "select version, status, mode, classification, probable_cause,"
                " confidence::float as confidence, responsible_system, requires_human_review,"
                " verification_notes, provider, model, ruleset_version"
                " from doctor.diagnoses where id = cast(:d as uuid)",
                d=report.diagnosis_id,
            )
            diagnosis = found[0] if found else None
            hypotheses = await rows(
                connection,
                "select rank, statement, confidence::float as confidence"
                " from doctor.diagnosis_hypotheses where diagnosis_id = cast(:d as uuid)"
                " order by rank",
                d=report.diagnosis_id,
            )
            evidence = await rows(
                connection,
                "select rank, kind, label, finding, event_id::text, event_timestamp,"
                " coalesce(event_id, raw_log_object_id, chunk_id, global_chunk_id,"
                " rule_match_id)::text as reference"
                " from doctor.diagnosis_evidence where diagnosis_id = cast(:d as uuid)"
                " order by rank",
                d=report.diagnosis_id,
            )
            for item in evidence:
                item["excerpt"] = (
                    await excerpt(connection, item["event_id"], item["event_timestamp"])
                    if report.include_event_excerpts and item["event_id"]
                    else None
                )
            recommendations = await rows(
                connection,
                "select rank, text, kind from doctor.diagnosis_recommendations"
                " where diagnosis_id = cast(:d as uuid) order by rank",
                d=report.diagnosis_id,
            )
        timeline, total = None, None
        if report.include_timeline:
            # Os Eventos das Execuções do Incidente, na janela delas (lê só as partições do mês).
            total = await connection.scalar(
                text(
                    "select count(*) from doctor.events e where e.execution_ref in ("
                    " select ie.execution_id from doctor.incident_executions ie"
                    " where ie.incident_id = cast(:i as uuid))"
                ),
                {"i": report.incident_id},
            )
            timeline = await rows(
                connection,
                "with runs as (select x.id, x.first_event_at, x.last_event_at"
                " from doctor.incident_executions ie join doctor.executions x"
                " on x.tenant_id = ie.tenant_id and x.id = ie.execution_id"
                " where ie.incident_id = cast(:i as uuid))"
                " select e.timestamp, e.operation, e.severity,"
                " coalesce(e.error ->> 'code', '') || case when e.error ->> 'message' is not null"
                " then ' ' || left(e.error ->> 'message', 200) else '' end as summary"
                " from doctor.events e where e.execution_ref in (select id from runs)"
                " and e.timestamp between (select min(first_event_at) from runs)"
                " and (select max(last_event_at) from runs)"
                " order by e.timestamp desc limit :n",
                i=report.incident_id,
                n=TIMELINE_LIMIT,
            )
            # Os mais recentes, em ordem cronológica.
            timeline.reverse()
    return ReportData(
        organization=str(organization or "Organização"),
        incident=incident,
        diagnosis=diagnosis,
        hypotheses=hypotheses,
        evidence=evidence,
        recommendations=recommendations,
        reviews=reviews,
        timeline=timeline,
        generated_at=datetime.now(UTC),
        timeline_total=int(total) if total is not None else None,
    )


async def finish(engine: AsyncEngine, report: Any, path: str, size: int, digest: str) -> None:
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text("select doctor.finish_report(cast(:r as uuid), :p, cast(:s as bigint), :h)"),
            {"r": report.id, "p": path, "s": size, "h": digest},
        )


class ReportBusyError(Exception):
    """Relatório em geração por outra entrega: a mensagem volta para a fila."""


async def still_running(engine: AsyncEngine, report_id: str) -> bool:
    async with engine.begin() as connection:
        await platform_role(connection)
        status = await connection.scalar(
            text("select status from doctor.reports where id = cast(:r as uuid)"), {"r": report_id}
        )
    return bool(status == "running")


async def give_up_or_release(engine: AsyncEngine, report: Any) -> bool:
    """Falha: volta à fila (o Pub/Sub reentrega) ou, na última tentativa, fica `failed`."""
    final = bool(report.attempts >= MAX_ATTEMPTS)
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "update doctor.reports set status = :s, error = :e"
                " where id = cast(:r as uuid) and status = 'running'"
            ),
            {
                "s": "failed" if final else "queued",
                "e": "Não foi possível gerar o relatório." if final else None,
                "r": report.id,
            },
        )
    return final


async def generate_report(engine: AsyncEngine, payload: Mapping[str, Any], storage: Storage) -> str:
    """`ready`, `failed` ou `ignored` (já pronto, ou outra entrega cuidando dele)."""
    report = await claim(engine, str(payload["report_id"]))
    if report is None:
        if await still_running(engine, str(payload["report_id"])):
            # Outra entrega tem a posse (ou caiu no meio): erro, para o Pub/Sub entregar de novo
            # depois do backoff, quando a posse vencida deixa retomar.
            raise ReportBusyError(str(payload["report_id"]))
        return "ignored"
    try:
        rendered = render(await load(engine, report), cast("Format", report.format))
        path = f"{report.tenant_id}/{report.id}.{report.format}"
        await storage.upload(REPORTS, path, rendered.content, rendered.content_type)
        await finish(engine, report, path, len(rendered.content), rendered.sha256)
    except Exception:
        log.exception("relatório %s: geração falhou", report.id)
        if await give_up_or_release(engine, report):
            return "failed"
        raise
    return "ready"
