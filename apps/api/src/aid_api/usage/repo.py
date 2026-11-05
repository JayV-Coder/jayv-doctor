"""Uso da Organização ativa, dentro de `tenant_tx`: as funções do banco leem só a dela."""

from sqlalchemy import text

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.usage.schemas import LlmUsage, ResourceUsage, Usage

ERRORS = {"42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação.")}


class UsageRepository:
    async def usage(self, claims: Claims) -> Usage:
        async with translated_tx(claims, ERRORS) as connection:
            tenant = (
                await connection.execute(
                    text(
                        "select plan, quota_tolerance::float as tolerance from doctor.tenants"
                        " where id = (select doctor.current_tenant_id())"
                    )
                )
            ).first()
            rows = await connection.execute(
                text("select resource, period, used, quota from doctor.my_usage()")
            )
            resources = [
                ResourceUsage(
                    resource=row.resource,
                    period=row.period,
                    used=int(row.used),
                    quota=int(row.quota),
                    ratio=round(int(row.used) / int(row.quota), 4) if row.quota else 0.0,
                )
                for row in rows
            ]
            llm = (
                await connection.execute(
                    text(
                        "select coalesce(sum(input_tokens), 0) as input_tokens,"
                        " coalesce(sum(output_tokens), 0) as output_tokens,"
                        " sum(cost_estimate)::float as cost_estimate from doctor.usage_llm"
                        # Mês em UTC, como o contador (timestamptz, sem depender do fuso da sessão).
                        " where created_at >= date_trunc('month', now(), 'UTC')"
                    )
                )
            ).one()
        return Usage(
            plan=tenant.plan if tenant else "pilot",
            tolerance=tenant.tolerance if tenant else 1.1,
            resources=resources,
            llm=LlmUsage(
                input_tokens=int(llm.input_tokens),
                output_tokens=int(llm.output_tokens),
                cost_estimate=llm.cost_estimate,
            ),
        )


def get_usage_repository() -> UsageRepository:
    return UsageRepository()
