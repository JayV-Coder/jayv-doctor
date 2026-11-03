"""Contratos de retenção e LGPD (ticket #29)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DataClass = Literal["raw_logs", "events", "incidents", "audit"]


class Retention(BaseModel):
    data_class: DataClass
    days: int
    default_days: int
    min_days: int
    max_days: int


class Deletion(BaseModel):
    requested_at: datetime
    scheduled_for: datetime


class PrivacySettings(BaseModel):
    retention: list[Retention]
    llm_enabled: bool
    llm_provider: Literal["anthropic", "vertex"]
    deletion: Deletion | None


class RetentionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_class: DataClass
    days: int = Field(ge=1, le=3650)


class LlmChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class DeletionRequest(BaseModel):
    """O Owner digita o slug da Organização para confirmar."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    confirmation: str = Field(min_length=1, max_length=100)


class SubjectQuery(BaseModel):
    """A Referência de negócio do titular (ex.: nº do pedido ou CPF) no corpo; vira HMAC com a
    chave da Organização e nunca chega ao banco nem aos logs."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reference: str = Field(min_length=1, max_length=200)


class SubjectEvents(BaseModel):
    events: int
    first_seen: datetime | None
    last_seen: datetime | None


class SubjectErased(BaseModel):
    events_erased: int
