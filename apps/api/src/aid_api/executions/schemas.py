"""Contratos do Explorador de Execuções (ticket #19)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ExecutionStatus = Literal["success", "failed", "pending_confirmation", "unknown"]
Environment = Literal["prd", "hml", "dev"]


class ExecutionSearch(BaseModel):
    """Busca no corpo, não na URL: o termo pode ser um número de pedido, e URL vai para os logs
    do Cloud Run e do proxy. A Referência de negócio vira HMAC no servidor antes de consultar."""

    model_config = ConfigDict(extra="forbid")

    q: str | None = Field(default=None, min_length=1, max_length=256)
    integration_id: UUID | None = None
    environment: Environment | None = None
    status: ExecutionStatus | None = None
    since: datetime | None = Field(default=None, alias="from")
    until: datetime | None = Field(default=None, alias="to")
    cursor: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=50, ge=1, le=50)


class IncidentRef(BaseModel):
    id: str
    title: str
    severity: str
    status: str


class ExecutionSummary(BaseModel):
    id: str
    integration_id: str
    integration_name: str
    environment: Environment
    status: ExecutionStatus
    low_confidence: bool
    first_event_at: datetime
    last_event_at: datetime
    duration_ms: int
    event_count: int
    closed_at: datetime | None
    correlation_keys: dict[str, list[str]]
    incident: IncidentRef | None


class ExecutionPage(BaseModel):
    items: list[ExecutionSummary]
    next_cursor: str | None


class TimelineEvent(BaseModel):
    id: str
    timestamp: datetime
    severity: str
    operation: str
    source: dict[str, Any]
    error: dict[str, Any] | None
    execution_id: str | None
    trace_id: str | None
    business_reference: str | None
    correlated_by: str | None
    # Regras cujo match aponta este Evento como prova (Evidência determinística).
    rule_codes: list[str]


class RuleHit(BaseModel):
    rule_code: str
    rule_version: str
    category: str
    description: str
    matched_event_ids: list[str]


class ExecutionDetail(ExecutionSummary):
    events: list[TimelineEvent]
    rules: list[RuleHit]


class RawLogRef(BaseModel):
    id: str
    source: str
    expires_at: datetime
    # Dias até a retenção apagar o Log bruto (ticket #29 traz a política por Organização).
    retention_days_left: int
    import_filename: str | None


class EventDetail(BaseModel):
    """O Evento normalizado inteiro (já sanitizado), para a Tela 9."""

    id: str
    execution_ref: str | None
    integration_id: str
    timestamp: datetime
    ingested_at: datetime
    schema_version: str
    severity: str
    operation: str
    source: dict[str, Any]
    error: dict[str, Any] | None
    execution_id: str | None
    trace_id: str | None
    business_context: dict[str, Any] | None
    attributes: dict[str, Any] | None
    sanitization_report: dict[str, Any] | None
    correlated_by: str | None
    raw_log: RawLogRef | None


class RawLogDownload(BaseModel):
    url: str
    expires_in: int
