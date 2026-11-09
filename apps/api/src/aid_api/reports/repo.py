"""Relatório técnico (ticket #32), dentro de `tenant_tx`: o RLS vale. A abertura pelo link roda
sem Usuário (`anonymous_tx`) e só alcança `doctor.open_report_share`."""

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

from aid_api.core.auth import Claims
from aid_api.core.db import anonymous_tx, translated_tx
from aid_api.core.errors import ApiError
from aid_api.reports.schemas import (
    ReportQueued,
    ReportRequest,
    ReportShare,
    ReportSummary,
)

ERRORS = {
    "P0002": lambda: ApiError(404, "not_found", "Não encontrado."),
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "23505": lambda: ApiError(
        409, "idempotency_conflict", "Chave de idempotência já usada em outro Incidente."
    ),
    "DR060": lambda: ApiError(409, "report_not_ready", "O relatório ainda não está pronto."),
}

SUMMARY = (
    "r.id::text, r.incident_id::text, r.diagnosis_id::text, d.version as diagnosis_version,"
    " r.format, r.include_timeline, r.include_event_excerpts, r.status, r.size_bytes,"
    " r.content_sha256, r.error, r.created_at, r.completed_at"
)
FROM = (
    " from doctor.reports r left join doctor.diagnoses d"
    " on d.tenant_id = r.tenant_id and d.id = r.diagnosis_id"
)


@dataclass(frozen=True)
class SharedFile:
    download_url: str
    format: str
    filename: str


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ReportRepository:
    async def request(
        self, claims: Claims, incident: str, body: ReportRequest, key: str
    ) -> ReportQueued:
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                await connection.execute(
                    text(
                        "select id::text, status from doctor.request_report("
                        "cast(:i as uuid), :f, :tl, :ex, :k)"
                    ),
                    {
                        "i": incident,
                        "f": body.format,
                        "tl": body.include_timeline,
                        "ex": body.include_event_excerpts,
                        "k": key,
                    },
                )
            ).one()
        return ReportQueued(report_id=row.id, status=row.status)

    async def for_incident(self, claims: Claims, incident: str) -> list[ReportSummary]:
        async with translated_tx(claims, ERRORS) as connection:
            exists = await connection.scalar(
                text("select 1 from doctor.incidents where id = cast(:i as uuid)"), {"i": incident}
            )
            if exists is None:
                raise ApiError(404, "not_found", "Incidente não encontrado.")
            result = await connection.execute(
                text(
                    f"select {SUMMARY}{FROM} where r.incident_id = cast(:i as uuid)"
                    " order by r.created_at desc limit 50"
                ),
                {"i": incident},
            )
            return [ReportSummary.model_validate(dict(row)) for row in result.mappings()]

    async def detail(
        self, claims: Claims, target: str, sign: Callable[[str], Awaitable[str]]
    ) -> tuple[ReportSummary, str | None, list[ReportShare]]:
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"select {SUMMARY}, r.storage_path{FROM} where r.id = cast(:r as uuid)"
                        ),
                        {"r": target},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise ApiError(404, "not_found", "Relatório não encontrado.")
            # O RLS dos links devolve vazio para o Viewer.
            shares = [
                ReportShare.model_validate(dict(item))
                for item in (
                    await connection.execute(
                        text(
                            "select id::text, expires_at, revoked_at, access_count,"
                            " last_accessed_at, created_at from doctor.report_shares"
                            " where report_id = cast(:r as uuid) order by created_at desc"
                        ),
                        {"r": target},
                    )
                ).mappings()
            ]
        summary = ReportSummary.model_validate(
            {k: v for k, v in row.items() if k != "storage_path"}
        )
        url = await sign(row["storage_path"]) if row["status"] == "ready" else None
        return summary, url, shares

    async def ready_path(self, claims: Claims, target: str) -> str:
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                await connection.execute(
                    text(
                        "select status, storage_path from doctor.reports"
                        " where id = cast(:r as uuid)"
                    ),
                    {"r": target},
                )
            ).first()
        if row is None:
            raise ApiError(404, "not_found", "Relatório não encontrado.")
        if row.status != "ready":
            raise ERRORS["DR060"]()
        return str(row.storage_path)

    async def share(
        self, claims: Claims, target: str, token: str, download_url: str
    ) -> tuple[str, datetime]:
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                await connection.execute(
                    text(
                        "select id::text, expires_at from doctor.create_report_share("
                        "cast(:r as uuid), :h, :u)"
                    ),
                    {"r": target, "h": token_hash(token), "u": download_url},
                )
            ).one()
        return row.id, row.expires_at

    async def revoke(self, claims: Claims, target: str, share: str) -> None:
        async with translated_tx(claims, ERRORS) as connection:
            found = await connection.scalar(
                text(
                    "select 1 from doctor.report_shares"
                    " where id = cast(:s as uuid) and report_id = cast(:r as uuid)"
                ),
                {"s": share, "r": target},
            )
            if found is None:
                raise ApiError(404, "not_found", "Link não encontrado.")
            await connection.execute(
                text("select doctor.revoke_report_share(cast(:s as uuid))"), {"s": share}
            )

    async def open_shared(self, token: str) -> SharedFile | None:
        async with anonymous_tx(ERRORS) as connection:
            row = (
                await connection.execute(
                    text("select download_url, format, filename from doctor.open_report_share(:h)"),
                    {"h": token_hash(token)},
                )
            ).first()
        if row is None:
            return None
        return SharedFile(row.download_url, row.format, row.filename)


def get_report_repository() -> ReportRepository:
    return ReportRepository()
