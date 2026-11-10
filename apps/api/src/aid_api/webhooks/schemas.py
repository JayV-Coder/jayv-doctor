"""Webhooks de saída assinados (ticket #42)."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
Event = Literal[
    "incident.opened",
    "incident.updated",
    "incident.resolved",
    "diagnosis.published",
    "diagnosis.reviewed",
]


class Webhook(BaseModel):
    id: str
    name: str
    url: str
    events: list[str]
    enabled: bool
    failure_count: int
    last_status: int | None
    last_delivery_at: datetime | None
    disabled_reason: str | None
    created_at: datetime


class WebhookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    url: str = Field(max_length=1000)
    events: list[Event] = Field(min_length=1, max_length=5)


class WebhookChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str | None = Field(default=None, max_length=1000)
    events: list[Event] | None = Field(default=None, min_length=1, max_length=5)
    enabled: bool | None = None


class WebhookSecret(BaseModel):
    # Aparece só aqui (criação e rotação): quem recebe guarda para conferir a assinatura.
    id: str
    secret: str


class Delivery(BaseModel):
    id: str
    event: str
    status: Literal["pending", "succeeded", "failed", "abandoned"]
    attempts: int
    response_status: int | None
    latency_ms: int | None
    response_excerpt: str | None
    error: str | None
    body: dict[str, Any] | None
    resent_from: str | None
    created_at: datetime
    delivered_at: datetime | None
    next_attempt_at: datetime | None
