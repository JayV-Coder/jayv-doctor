"""Regras de alerta, canais, push e silêncio (ticket #41)."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class AlertRule(BaseModel):
    id: str
    name: str
    enabled: bool
    conditions: dict[str, Any]
    channels: list[str]
    quiet_hours: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class AlertRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    enabled: bool = True
    conditions: dict[str, Any]
    channels: list[str] = Field(default_factory=list, max_length=10)
    quiet_hours: dict[str, Any] | None = None


class AlertRuleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    enabled: bool | None = None
    conditions: dict[str, Any] | None = None
    channels: list[str] | None = Field(default=None, max_length=10)
    quiet_hours: dict[str, Any] | None = None
    clear_quiet_hours: bool = False


class Channel(BaseModel):
    id: str
    type: Literal["email", "slack", "teams", "webpush"]
    name: str
    config: dict[str, Any]
    created_at: datetime


class ChannelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["email", "slack", "teams", "webpush"]
    name: Name
    # email e webpush: quem recebe (só Usuários da Organização).
    audience: Literal["managers", "all"] = "managers"
    # slack e teams: o webhook, que vai para o Vault e não volta em nenhuma resposta.
    webhook_url: str | None = Field(default=None, max_length=1000)


class PushKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p256dh: str = Field(min_length=40, max_length=200)
    auth: str = Field(min_length=10, max_length=100)


class PushSubscriptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(max_length=1000)
    keys: PushKeys
    user_agent: str | None = Field(default=None, max_length=300)


class PushSubscription(BaseModel):
    id: str
    endpoint: str
    user_agent: str | None
    last_success_at: datetime | None
    created_at: datetime


class PushKey(BaseModel):
    # Nulo onde o push não está configurado (sem VAPID): a tela esconde a opção.
    public_key: str | None


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiet_hours: dict[str, Any] | None = None
