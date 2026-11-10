"""Contratos do Diagnóstico (ticket #24). A Confiança é heurística (não calibrada)."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    kind: Literal["event", "raw_log", "chunk", "global_chunk", "rule_match", "enrichment"]
    # Nulo quando a retenção já apagou o registro apontado; `label` guarda o que ele era.
    ref_id: str | None
    # Instante do Evento a abrir (o próprio, ou o primeiro da Regra).
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


System = Literal["sap", "salesforce", "gcp", "other"]


class FeedbackRequest(BaseModel):
    """Aceitar, Corrigir (com a categoria ou a causa certa) ou Rejeitar uma versão."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    verdict: Literal["accepted", "corrected", "rejected"]
    correct_category: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,59}$")
    correct_cause: str | None = Field(default=None, min_length=1, max_length=2000)
    responsible_system: System | None = None
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.verdict == "corrected" and not (self.correct_category or self.correct_cause):
            raise ValueError("corrigir exige a categoria ou a causa certa")
        return self


class Feedback(BaseModel):
    id: str
    verdict: Literal["accepted", "corrected", "rejected"]
    correct_category: str | None
    correct_cause: str | None
    responsible_system: System | None
    comment: str | None
    reviewer_id: str | None
    time_to_review_s: int | None
    created_at: datetime


class Promoted(BaseModel):
    document_id: str


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
    feedback: list[Feedback]


class DiagnosisSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_diagnose_critical: bool
