"""Saída pedida ao LLM na etapa 5 (o schema do PRD). Tudo nela é conferido na etapa 6."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

System = Literal["sap", "salesforce", "gcp", "other", "indeterminado"]


class EvidenceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(max_length=100, description="Identificador `ref` de um dado fornecido.")
    finding: str = Field(min_length=1, max_length=500, description="O que esse dado mostra.")


class HypothesisOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)


class RecommendationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500, description="Ação para uma pessoa executar.")
    kind: Literal["investigate", "fix", "verify"]


class LLMDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: str = Field(
        pattern=r"^[A-Z][A-Z0-9_]{2,59}$",
        description="Código da classificação, ex.: UPSTREAM_TIMEOUT.",
    )
    status: Literal["IDENTIFIED", "INCONCLUSIVE"]
    probable_cause: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1, description="Confiança heurística, de 0 a 1.")
    responsible_system: System
    evidence: list[EvidenceOut] = Field(max_length=12)
    hypotheses: list[HypothesisOut] = Field(default_factory=list, max_length=5)
    recommendations: list[RecommendationOut] = Field(max_length=6)
    requires_human_review: bool
