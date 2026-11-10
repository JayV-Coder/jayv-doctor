"""Alertas dentro de `tenant_tx`: o RLS limita à Organização ativa; Regras e canais só Owner e
Admin com MFA escrevem; push e silêncio, cada Usuário os seus."""

import json
from typing import Any

from aid_alerts import (
    AlertError,
    dump_quiet_hours,
    parse_conditions,
    parse_quiet_hours,
    push_endpoint_allowed,
    webhook_allowed,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_api.alerts.schemas import (
    AlertRule,
    AlertRuleChange,
    AlertRuleIn,
    Channel,
    ChannelIn,
    Preferences,
    PushSubscription,
    PushSubscriptionIn,
)
from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError

RULE_COLUMNS = "id::text, name, enabled, conditions, channels, quiet_hours, created_at, updated_at"
CHANNEL_COLUMNS = "id::text, type, name, config, created_at"
PUSH_COLUMNS = "id::text, endpoint, user_agent, last_success_at, created_at"


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Regra, canal ou assinatura não encontrada.")


def forbidden() -> ApiError:
    return ApiError(403, "forbidden", "Seu Papel não permite esta ação.")


ERRORS = {
    "23505": lambda: ApiError(409, "name_taken", "Já existe um item com este nome."),
    "42501": forbidden,
    "P0002": not_found,
}


def invalid(detail: str) -> ApiError:
    return ApiError(422, "invalid_alert", f"Configuração inválida ({detail}).")


def clean_conditions(raw: dict[str, Any]) -> str:
    try:
        return json.dumps(parse_conditions(raw).as_json())
    except AlertError as exc:
        raise invalid(str(exc)) from exc


def clean_quiet(raw: dict[str, Any] | None) -> str | None:
    try:
        found = dump_quiet_hours(parse_quiet_hours(raw))
    except AlertError as exc:
        raise invalid(str(exc)) from exc
    return json.dumps(found) if found else None


async def clean_channels(connection: AsyncConnection, channels: list[str]) -> str:
    """Só canais desta Organização (o RLS de leitura já filtra)."""
    found = await connection.execute(
        text(
            "select id::text from doctor.notification_channels"
            " where id::text = any(cast(:c as text[]))"
        ),
        {"c": channels},
    )
    known = {row[0] for row in found}
    if set(channels) - known:
        raise invalid("channels: canais desta Organização")
    return json.dumps(sorted(set(channels)))


class AlertRepository:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self.engine = engine

    async def rules(self, claims: Claims) -> list[AlertRule]:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            result = await connection.execute(
                text(f"select {RULE_COLUMNS} from doctor.alert_rules order by name")  # noqa: S608
            )
            return [AlertRule.model_validate(dict(row)) for row in result.mappings()]

    async def create_rule(self, claims: Claims, new: AlertRuleIn) -> AlertRule:
        conditions, quiet = clean_conditions(new.conditions), clean_quiet(new.quiet_hours)
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            channels = await clean_channels(connection, new.channels)
            row = (
                (
                    await connection.execute(
                        text(
                            "insert into doctor.alert_rules (name, enabled, conditions, channels,"  # noqa: S608
                            " quiet_hours) values (:n, :e, cast(:c as jsonb), cast(:ch as jsonb),"
                            f" cast(:q as jsonb)) returning {RULE_COLUMNS}"
                        ),
                        {
                            "n": new.name,
                            "e": new.enabled,
                            "c": conditions,
                            "ch": channels,
                            "q": quiet,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise forbidden()
            return AlertRule.model_validate(dict(row))

    async def update_rule(self, claims: Claims, target: str, change: AlertRuleChange) -> AlertRule:
        values: dict[str, Any] = {}
        if change.name is not None:
            values["name"] = change.name
        if change.enabled is not None:
            values["enabled"] = change.enabled
        if change.conditions is not None:
            values["conditions"] = clean_conditions(change.conditions)
        if change.quiet_hours is not None:
            values["quiet_hours"] = clean_quiet(change.quiet_hours)
        elif change.clear_quiet_hours:
            values["quiet_hours"] = None
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            if change.channels is not None:
                values["channels"] = await clean_channels(connection, change.channels)
            jsonb = {"conditions", "channels", "quiet_hours"}
            assignments = ", ".join(
                f"{name} = cast(:{name} as jsonb)" if name in jsonb else f"{name} = :{name}"
                for name in values
            )
            if not values:
                assignments = "name = name"
            row = (
                (
                    await connection.execute(
                        text(
                            f"update doctor.alert_rules set {assignments}"  # noqa: S608
                            f" where id = cast(:target as uuid) returning {RULE_COLUMNS}"
                        ),
                        {**values, "target": target},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                exists = await connection.scalar(
                    text("select 1 from doctor.alert_rules where id = cast(:t as uuid)"),
                    {"t": target},
                )
                raise forbidden() if exists else not_found()
            return AlertRule.model_validate(dict(row))

    async def delete_rule(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            deleted = await connection.scalar(
                text("delete from doctor.alert_rules where id = cast(:t as uuid) returning id"),
                {"t": target},
            )
            if deleted is None:
                exists = await connection.scalar(
                    text("select 1 from doctor.alert_rules where id = cast(:t as uuid)"),
                    {"t": target},
                )
                raise forbidden() if exists else not_found()

    async def channels(self, claims: Claims) -> list[Channel]:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            result = await connection.execute(
                text(f"select {CHANNEL_COLUMNS} from doctor.notification_channels order by name")  # noqa: S608
            )
            return [Channel.model_validate(dict(row)) for row in result.mappings()]

    async def create_channel(self, claims: Claims, new: ChannelIn) -> Channel:
        secret: str | None = None
        config: dict[str, Any] = {}
        if new.type in ("slack", "teams"):
            if not new.webhook_url or not webhook_allowed(new.type, new.webhook_url):
                raise invalid(f"webhook_url: endereço de webhook do {new.type} (HTTPS)")
            secret = new.webhook_url
        else:
            if new.webhook_url:
                raise invalid("webhook_url: só para Slack e Teams")
            config = {"audience": new.audience}
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            created = await connection.scalar(
                text(
                    "select doctor.create_notification_channel(:k, :n, cast(:c as jsonb), :s)::text"
                ),
                {"k": new.type, "n": new.name, "c": json.dumps(config), "s": secret},
            )
            row = (
                (
                    await connection.execute(
                        text(
                            f"select {CHANNEL_COLUMNS} from doctor.notification_channels"  # noqa: S608
                            " where id = cast(:c as uuid)"
                        ),
                        {"c": created},
                    )
                )
                .mappings()
                .one()
            )
            return Channel.model_validate(dict(row))

    async def delete_channel(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text("select doctor.delete_notification_channel(cast(:c as uuid))"), {"c": target}
            )

    async def subscriptions(self, claims: Claims) -> list[PushSubscription]:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            result = await connection.execute(
                text(f"select {PUSH_COLUMNS} from doctor.push_subscriptions order by created_at")  # noqa: S608
            )
            return [PushSubscription.model_validate(dict(row)) for row in result.mappings()]

    async def subscribe(self, claims: Claims, new: PushSubscriptionIn) -> PushSubscription:
        if not push_endpoint_allowed(new.endpoint):
            raise invalid("endpoint: serviço de push de um navegador")
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            # Mesmo aparelho de novo (chaves renovadas): troca a assinatura.
            await connection.execute(
                text("delete from doctor.push_subscriptions where endpoint = :e"),
                {"e": new.endpoint},
            )
            row = (
                (
                    await connection.execute(
                        text(
                            "insert into doctor.push_subscriptions (endpoint, p256dh, auth,"  # noqa: S608
                            f" user_agent) values (:e, :p, :a, :u) returning {PUSH_COLUMNS}"
                        ),
                        {
                            "e": new.endpoint,
                            "p": new.keys.p256dh,
                            "a": new.keys.auth,
                            "u": new.user_agent,
                        },
                    )
                )
                .mappings()
                .one()
            )
            return PushSubscription.model_validate(dict(row))

    async def unsubscribe(self, claims: Claims, target: str) -> None:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            deleted = await connection.scalar(
                text(
                    "delete from doctor.push_subscriptions where id = cast(:t as uuid) returning id"
                ),
                {"t": target},
            )
            if deleted is None:
                raise not_found()

    async def preferences(self, claims: Claims) -> Preferences:
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            found = await connection.scalar(
                text("select quiet_hours from doctor.alert_preferences limit 1")
            )
            return Preferences(quiet_hours=found)

    async def save_preferences(self, claims: Claims, change: Preferences) -> Preferences:
        quiet = clean_quiet(change.quiet_hours)
        async with translated_tx(claims, ERRORS, self.engine) as connection:
            await connection.execute(
                text(
                    "insert into doctor.alert_preferences (quiet_hours)"
                    " values (cast(:q as jsonb)) on conflict (tenant_id, user_id)"
                    " do update set quiet_hours = excluded.quiet_hours"
                ),
                {"q": quiet},
            )
            return Preferences(quiet_hours=json.loads(quiet) if quiet else None)


def get_alert_repository() -> AlertRepository:
    return AlertRepository()
