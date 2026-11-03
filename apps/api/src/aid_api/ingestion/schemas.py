"""Contratos dos tokens de ingestão e de POST /ingestion/events."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NewIngestionToken(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=80)
    integration_id: UUID


class CreatedIngestionToken(BaseModel):
    id: str
    # Mostrado uma vez só: o banco guarda o sha256.
    token: str
    prefix: str


class IngestionToken(BaseModel):
    id: str
    name: str
    integration_id: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class RejectedEvent(BaseModel):
    index: int
    reason: str


class IngestionResult(BaseModel):
    accepted: int
    rejected: list[RejectedEvent]
