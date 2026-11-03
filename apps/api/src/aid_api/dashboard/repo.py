"""Leituras do Dashboard dentro de `tenant_tx`, com o RLS. Execuções e falhas saem do agregado
por hora (`execution_stats_hourly`); Incidentes e MTTR, da tabela de Incidentes."""

from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.dashboard.schemas import (
    Bucket,
    CategoryCount,
    Dashboard,
    IncidentRow,
    Kpi,
    Period,
)
from aid_api.dashboard.service import change, error_rate

SPANS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

INCIDENT_ROW = (
    "n.id::text as id, n.number, n.title, n.severity, n.status, n.category,"
    " i.name as integration_name, i.environment, n.first_seen_at, n.last_seen_at,"
    " n.execution_count"
    " from doctor.incidents n"
    " join doctor.integrations i on i.tenant_id = n.tenant_id and i.id = n.integration_id"
)


def scope(environment: str | None, integration_id: UUID | None) -> tuple[str, dict[str, Any]]:
    """Filtros de Ambiente e Integração, aplicados pelo alias `i` (integrations)."""
    conditions = ""
    params: dict[str, Any] = {}
    if environment:
        conditions += " and i.environment = :environment"
        params["environment"] = environment
    if integration_id:
        conditions += " and i.id = cast(:integration as uuid)"
        params["integration"] = str(integration_id)
    return conditions, params


async def totals(
    connection: AsyncConnection,
    extra: str,
    params: dict[str, Any],
    previous: datetime,
    start: datetime,
    end: datetime,
) -> tuple[int, int, int, int]:
    """(total, falhas) do período e do anterior, numa consulta só."""
    row = (
        await connection.execute(
            text(
                "select"  # noqa: S608
                " coalesce(sum(s.total) filter (where s.hour >= :start), 0)::int as total,"
                " coalesce(sum(s.failed) filter (where s.hour >= :start), 0)::int as failed,"
                " coalesce(sum(s.total) filter (where s.hour < :start), 0)::int as before_total,"
                " coalesce(sum(s.failed) filter (where s.hour < :start), 0)::int as before_failed"
                " from doctor.execution_stats_hourly s join doctor.integrations i"
                " on i.tenant_id = s.tenant_id and i.id = s.integration_id"
                f" where s.hour >= :previous and s.hour < :end{extra}"
            ),
            {**params, "previous": previous, "start": start, "end": end},
        )
    ).one()
    return row.total, row.failed, row.before_total, row.before_failed


async def mttr(
    connection: AsyncConnection,
    extra: str,
    params: dict[str, Any],
    previous: datetime,
    start: datetime,
    end: datetime,
) -> tuple[float | None, float | None]:
    """Média de resolved_at - first_seen_at dos resolvidos em cada período, em minutos.
    Reaberto perde o resolved_at e só conta de novo quando voltar a ser resolvido."""
    row = (
        await connection.execute(
            text(
                "select"  # noqa: S608
                " avg(extract(epoch from (n.resolved_at - n.first_seen_at)) / 60)"
                "  filter (where n.resolved_at >= :start) as current,"
                " avg(extract(epoch from (n.resolved_at - n.first_seen_at)) / 60)"
                "  filter (where n.resolved_at < :start) as before"
                " from doctor.incidents n join doctor.integrations i"
                " on i.tenant_id = n.tenant_id and i.id = n.integration_id"
                " where n.status = 'resolved' and n.resolved_at >= :previous"
                f" and n.resolved_at < :end{extra}"
            ),
            {**params, "previous": previous, "start": start, "end": end},
        )
    ).one()

    def minutes(value: Any) -> float | None:
        return round(float(value), 1) if value is not None else None

    return minutes(row.current), minutes(row.before)


class DashboardRepository:
    async def load(
        self,
        claims: Claims,
        period: Period,
        environment: str | None,
        integration_id: UUID | None,
        now: datetime,
    ) -> Dashboard:
        span = SPANS[period]
        start, previous = now - span, now - 2 * span
        bucket: Literal["hour", "day"] = "hour" if period == "24h" else "day"
        extra, params = scope(environment, integration_id)
        async with translated_tx(claims, {}) as connection:
            total, failed, before_total, before_failed = await totals(
                connection, extra, params, previous, start, now
            )
            current_mttr, previous_mttr = await mttr(
                connection, extra, params, previous, start, now
            )
            # Série completa, em UTC: intervalo sem falha aparece como zero, não some.
            failures = [
                Bucket.model_validate(dict(row))
                for row in (
                    await connection.execute(
                        text(
                            "with series as (select generate_series("  # noqa: S608
                            " date_trunc(:bucket, cast(:start as timestamptz), 'UTC'),"
                            " date_trunc(:bucket, cast(:end as timestamptz), 'UTC'),"
                            " cast(:step as interval)) as start),"
                            " sums as (select date_trunc(:bucket, s.hour, 'UTC') as start,"
                            " sum(s.total)::int as total, sum(s.failed)::int as failed"
                            " from doctor.execution_stats_hourly s join doctor.integrations i"
                            " on i.tenant_id = s.tenant_id and i.id = s.integration_id"
                            f" where s.hour >= :start and s.hour < :end{extra} group by 1)"
                            " select series.start, coalesce(sums.total, 0) as total,"
                            " coalesce(sums.failed, 0) as failed"
                            " from series left join sums using (start) order by 1"
                        ),
                        {
                            **params,
                            "bucket": bucket,
                            "step": timedelta(hours=1) if bucket == "hour" else timedelta(days=1),
                            "start": start,
                            "end": now,
                        },
                    )
                ).mappings()
            ]
            categories = [
                CategoryCount.model_validate(dict(row))
                for row in (
                    await connection.execute(
                        text(
                            "select c.key as category, sum(c.value::int)::int as count"  # noqa: S608
                            " from doctor.execution_stats_hourly s join doctor.integrations i"
                            " on i.tenant_id = s.tenant_id and i.id = s.integration_id"
                            " cross join lateral jsonb_each_text(s.by_category) c"
                            f" where s.hour >= :start and s.hour < :end{extra}"
                            " group by c.key order by 2 desc, 1"
                        ),
                        {**params, "start": start, "end": now},
                    )
                ).mappings()
            ]
            open_incidents = await connection.scalar(
                text(
                    "select count(*)::int from doctor.incidents n"  # noqa: S608
                    " join doctor.integrations i"
                    " on i.tenant_id = n.tenant_id and i.id = n.integration_id"
                    f" where n.status in ('open', 'investigating'){extra}"
                ),
                params,
            )
            critical = (
                (
                    await connection.execute(
                        text(
                            f"select {INCIDENT_ROW}"
                            " where n.status in ('open', 'investigating')"
                            f" and n.severity = 'critical'{extra}"
                            " order by n.last_seen_at desc limit 1"
                        ),
                        params,
                    )
                )
                .mappings()
                .first()
            )
            recent = [
                IncidentRow.model_validate(dict(row))
                for row in (
                    await connection.execute(
                        text(
                            f"select {INCIDENT_ROW} where true{extra}"
                            " order by n.last_seen_at desc limit 5"
                        ),
                        params,
                    )
                ).mappings()
            ]
            baseline = await connection.scalar(
                text(
                    "select mttr_baseline_minutes from doctor.tenants"
                    " where id = doctor.current_tenant_id()"
                )
            )
        rate, before_rate = error_rate(total, failed), error_rate(before_total, before_failed)
        return Dashboard(
            period=period,
            bucket=bucket,
            executions=Kpi(value=total, previous=before_total, change=change(total, before_total)),
            error_rate=Kpi(value=rate, previous=before_rate, change=change(rate, before_rate)),
            mttr_minutes=Kpi(
                value=current_mttr,
                previous=previous_mttr,
                change=change(current_mttr, previous_mttr),
            ),
            open_incidents=int(open_incidents or 0),
            mttr_baseline_minutes=baseline,
            mttr_vs_baseline=change(current_mttr, baseline),
            failures=failures,
            failures_by_category=categories,
            critical_incident=IncidentRow.model_validate(dict(critical)) if critical else None,
            recent_incidents=recent,
        )


def get_dashboard_repository() -> DashboardRepository:
    return DashboardRepository()
