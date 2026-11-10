"""Webhooks dentro de `tenant_tx`: só Owner e Admin com MFA veem e mudam (o RLS e as funções
do banco conferem o Papel na tabela)."""

from typing import Any

from aid_alerts.network import UnsafeUrlError, check_url
from aid_alerts.signing import new_secret
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.webhooks.schemas import Delivery, Webhook, WebhookChange, WebhookIn, WebhookSecret

COLUMNS = (
    "id::text, name, url, events, enabled, failure_count, last_status, last_delivery_at,"
    " disabled_reason, created_at"
)
DELIVERY_COLUMNS = (
    "id::text, event, status, attempts, response_status, latency_ms, response_excerpt, error,"
    " body, resent_from::text, created_at, delivered_at, next_attempt_at"
)


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Webhook ou entrega não encontrada.")


ERRORS = {
    "23505": lambda: ApiError(409, "name_taken", "Já existe um webhook com este nome."),
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "P0002": not_found,
}


async def safe_url(url: str) -> str:
    try:
        await check_url(url)
    except UnsafeUrlError as exc:
        raise ApiError(422, "unsafe_url", f"Endereço recusado ({exc}).") from exc
    return url


class WebhookRepository:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self.engine = engine

    async def all(self, claims: Claims) -> list[Webhook]:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            result = await connection.execute(
                text(f"select {COLUMNS} from doctor.webhooks order by name")  # noqa: S608
            )
            return [Webhook.model_validate(dict(row)) for row in result.mappings()]

    async def create(self, claims: Claims, new: WebhookIn) -> WebhookSecret:
        url = await safe_url(new.url)
        secret = new_secret()
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            created = await connection.scalar(
                text("select doctor.create_webhook(:n, :u, cast(:e as text[]), :s)::text"),
                {"n": new.name, "u": url, "e": sorted(set(new.events)), "s": secret},
            )
        return WebhookSecret(id=str(created), secret=secret)

    async def update(self, claims: Claims, target: str, change: WebhookChange) -> Webhook:
        url = await safe_url(change.url) if change.url is not None else None
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.update_webhook(cast(:w as uuid), :u, cast(:e as text[]), :on)"),
                {
                    "w": target,
                    "u": url,
                    "e": sorted(set(change.events)) if change.events else None,
                    "on": change.enabled,
                },
            )
            row = (
                (
                    await connection.execute(
                        text(f"select {COLUMNS} from doctor.webhooks where id = cast(:w as uuid)"),  # noqa: S608
                        {"w": target},
                    )
                )
                .mappings()
                .one()
            )
            return Webhook.model_validate(dict(row))

    async def rotate(self, claims: Claims, target: str) -> WebhookSecret:
        secret = new_secret()
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.rotate_webhook_secret(cast(:w as uuid), :s)"),
                {"w": target, "s": secret},
            )
        return WebhookSecret(id=target, secret=secret)

    async def delete(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.delete_webhook(cast(:w as uuid))"), {"w": target}
            )

    async def deliveries(self, claims: Claims, target: str) -> list[Delivery]:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            exists = await connection.scalar(
                text("select 1 from doctor.webhooks where id = cast(:w as uuid)"), {"w": target}
            )
            if exists is None:
                raise not_found()
            result = await connection.execute(
                text(
                    f"select {DELIVERY_COLUMNS} from doctor.webhook_deliveries"  # noqa: S608
                    " where webhook_id = cast(:w as uuid) order by created_at desc limit 50"
                ),
                {"w": target},
            )
            return [Delivery.model_validate(dict(row)) for row in result.mappings()]

    async def resend(self, claims: Claims, target: str) -> dict[str, Any]:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            created = await connection.scalar(
                text("select doctor.resend_webhook_delivery(cast(:d as uuid))::text"),
                {"d": target},
            )
        return {"id": str(created)}


def get_webhook_repository() -> WebhookRepository:
    return WebhookRepository()
