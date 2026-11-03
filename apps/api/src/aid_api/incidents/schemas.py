"""Contratos de Incidentes (ticket #20)."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Status = Literal["open", "investigating", "resolved", "dismissed"]
Severity = Literal["low", "medium", "high", "critical"]


class IncidentSearch(BaseModel):
    """Filtros no corpo (POST), como na busca de Execuções: `q` pode ser um nº de pedido."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, min_length=1, max_length=256)
    status: list[Status] | None = None
    severity: list[Severity] | None = None
    category: str | None = Field(default=None, max_length=40)
    integration_id: UUID | None = None
    environment: Literal["prd", "hml", "dev"] | None = None
    assignee_id: UUID | None = None
    since: datetime | None = Field(default=None, alias="from")
    until: datetime | None = Field(default=None, alias="to")
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)


class IncidentSummary(BaseModel):
    id: str
    number: int
    title: str
    category: str
    severity: Severity
    status: Status
    rule_code: str
    rule_version: str
    integration_id: str
    integration_name: str
    environment: Literal["prd", "hml", "dev"]
    first_seen_at: datetime
    last_seen_at: datetime
    execution_count: int
    assignee_id: str | None
    resolved_at: datetime | None


class IncidentPage(BaseModel):
    items: list[IncidentSummary]
    next_cursor: str | None
    # Contagem por status com os outros filtros aplicados (chips da Tela 5).
    counts: dict[str, int]


class IncidentExecution(BaseModel):
    id: str
    status: str
    first_event_at: datetime
    duration_ms: int
    event_count: int
    correlation_keys: dict[str, list[str]]


class RuleEvidence(BaseModel):
    """Evidência determinística: a Regra que disparou e os Eventos que ela usou como prova."""

    execution_id: str
    rule_code: str
    rule_version: str
    category: str
    description: str
    matched_event_ids: list[str]


class HistoryEntry(BaseModel):
    action: str
    from_value: str | None
    to_value: str | None
    note: str | None
    actor_id: str | None
    created_at: datetime


class Comment(BaseModel):
    id: str
    author_id: str | None
    body_md: str
    mentions: list[str]
    created_at: datetime


class IncidentDetail(IncidentSummary):
    resolution_note: str | None
    executions: list[IncidentExecution]
    evidence: list[RuleEvidence]
    history: list[HistoryEntry]


class IncidentChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Status | None = None
    severity: Severity | None = None
    assignee_id: UUID | None = None
    resolution_note: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def check(self) -> Self:
        sent = self.model_fields_set
        if not sent:
            raise ValueError("nada a alterar")
        if self.status == "resolved" and not (self.resolution_note or "").strip():
            raise ValueError("resolver exige nota de resolução")
        if ("status" in sent and self.status is None) or (
            "severity" in sent and self.severity is None
        ):
            raise ValueError("status e severidade não podem ser nulos")
        return self


class NewComment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body_md: str = Field(min_length=1, max_length=4000)
    mentions: list[UUID] = Field(default_factory=list, max_length=20)
