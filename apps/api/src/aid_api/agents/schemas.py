"""Gestão dos agentes locais (ticket #39)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Agent(BaseModel):
    id: str
    integration_id: str
    name: str
    status: Literal["pending", "active", "revoked"]
    config: dict[str, Any]
    config_version: int
    cert_fingerprint: str | None
    version: str | None
    last_seen_at: datetime | None
    registered_at: datetime | None
    revoked_at: datetime | None
    registration_expires_at: datetime | None
    created_at: datetime


class NewAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=80)
    integration_id: UUID
    config: dict[str, Any] = Field(default_factory=lambda: {"collections": []})


class AgentConfigChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]


class RegistrationToken(BaseModel):
    id: str
    # Aparece uma vez: vale 24 h para um registro.
    registration_token: str
    expires_in_hours: int
    install_command: str
