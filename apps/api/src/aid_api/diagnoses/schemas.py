"""Contratos do Diagnóstico (ticket #24). A Confiança é heurística (não calibrada)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Status = Literal["queued", "running", "published", "inconclusive", "failed_llm", "failed"]
StageName = Literal[
    "queued", "validation", "correlation", "rules", "knowledge", "llm", "verification", "done"
]
Mode = Literal["hybrid", "rules_only"]


class DiagnosisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode = "hybrid"
    include_knowledge_base: bool = True


class DiagnosisQueued(BaseModel):
    diagnosis_id: str
    status: Status
    version: int


class DiagnosisSummary(BaseModel):
    id: str
    incident_id: str
    version: int
    status: Status
    stage: StageName
    requested_mode: Mode
    mode: Mode
    classification: str | None
    confidence: float | None
    requires_human_review: bool
    created_at: datetime
    published_at: datetime | None


class Hypothesis(BaseModel):
    rank: int
    statement: str
    confidence: float | None


class Evidence(BaseModel):
    rank: int
    kind: Literal["event", "raw_log", "chunk", "global_chunk", "rule_match"]
    # Nulo quando a retenção já apagou o registro apontado; `label` guarda o que ele era.
    ref_id: str | None
    event_timestamp: datetime | None
    label: str
    finding: str
    # Para o link da tela: o Evento a abrir (o próprio, ou o primeiro que a Regra apontou) e a
    # Execução da Timeline. Nulos para a Base de conhecimento.
    event_id: str | None
    execution_id: str | None


class Recommendation(BaseModel):
    rank: int
    text: str
    kind: Literal["investigate", "fix", "verify"]


class DiagnosisDetail(DiagnosisSummary):
    probable_cause: str | None
    # null = Indeterminado.
    responsible_system: Literal["sap", "salesforce", "gcp", "other"] | None
    include_knowledge_base: bool
    verification_notes: list[str]
    provider: str | None
    model: str | None
    ruleset_version: str | None
    input_tokens: int
    output_tokens: int
    duration_ms: int | None
    error: str | None
    hypotheses: list[Hypothesis]
    evidence: list[Evidence]
    recommendations: list[Recommendation]


class DiagnosisSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_diagnose_critical: bool
