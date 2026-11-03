"""Retenção e LGPD dentro de `tenant_tx`; as funções do banco conferem Papel e MFA."""

from sqlalchemy import text

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.privacy.schemas import (
    Deletion,
    DeletionRequest,
    PrivacySettings,
    Retention,
    RetentionChange,
    SubjectEvents,
)

CLASSES = ("raw_logs", "events", "incidents", "audit")
ERRORS = {
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "DR040": lambda: ApiError(422, "retention_out_of_bounds", "Retenção fora dos limites."),
    "DR041": lambda: ApiError(
        422, "confirmation_mismatch", "Digite o identificador (slug) da Organização para confirmar."
    ),
    "22023": lambda: ApiError(422, "validation_error", "Valor inválido."),
}


class PrivacyRepository:
    async def settings(self, claims: Claims) -> PrivacySettings:
        async with translated_tx(claims, ERRORS) as connection:
            tenant = (
                await connection.execute(
                    text(
                        "select llm_enabled, llm_provider, deletion_requested_at,"
                        " deletion_scheduled_for from doctor.tenants"
                        " where id = (select doctor.current_tenant_id())"
                    )
                )
            ).one()
            retention = []
            for data_class in CLASSES:
                row = (
                    await connection.execute(
                        text(
                            "select doctor.effective_retention((select doctor.current_tenant_id()),"
                            " :c) as days, b.default_days, b.min_days, b.max_days"
                            " from doctor.retention_bounds(:c) b"
                        ),
                        {"c": data_class},
                    )
                ).one()
                retention.append(
                    Retention.model_validate({"data_class": data_class, **row._mapping})
                )
        deletion = (
            Deletion(
                requested_at=tenant.deletion_requested_at,
                scheduled_for=tenant.deletion_scheduled_for,
            )
            if tenant.deletion_requested_at
            else None
        )
        return PrivacySettings(
            retention=retention,
            llm_enabled=tenant.llm_enabled,
            llm_provider=tenant.llm_provider,
            deletion=deletion,
        )

    async def set_retention(self, claims: Claims, change: RetentionChange) -> None:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(
                text("select doctor.set_retention_policy(:c, :d)"),
                {"c": change.data_class, "d": change.days},
            )

    async def set_llm(self, claims: Claims, enabled: bool) -> None:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(text("select doctor.set_llm_enabled(:e)"), {"e": enabled})

    async def request_deletion(self, claims: Claims, request: DeletionRequest) -> None:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(
                text("select doctor.request_tenant_deletion(:c)"), {"c": request.confirmation}
            )

    async def cancel_deletion(self, claims: Claims) -> None:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(text("select doctor.cancel_tenant_deletion()"))

    async def find_subject(self, claims: Claims, reference: str) -> SubjectEvents:
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                await connection.execute(
                    text(
                        "select events, first_seen, last_seen from doctor.find_subject_events(:r)"
                    ),
                    {"r": reference},
                )
            ).one()
        return SubjectEvents.model_validate(dict(row._mapping))

    async def erase_subject(self, claims: Claims, reference: str) -> int:
        async with translated_tx(claims, ERRORS) as connection:
            removed = await connection.scalar(
                text("select doctor.erase_subject_events(:r)"), {"r": reference}
            )
        return int(removed or 0)


def get_privacy_repository() -> PrivacyRepository:
    return PrivacyRepository()
