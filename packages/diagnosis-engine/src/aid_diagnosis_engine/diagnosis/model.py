"""Dados que entram e saem do motor. O worker carrega o contexto (sempre do tenant do Incidente)
pelo `Loader`; o motor não toca no banco."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from aid_diagnosis_engine.rules.base import EventView

Stage = Literal["validation", "correlation", "rules", "knowledge", "llm", "verification"]
Mode = Literal["hybrid", "rules_only"]
Status = Literal["published", "inconclusive", "failed_llm"]
EvidenceKind = Literal["event", "chunk", "global_chunk", "rule_match"]
RecommendationKind = Literal["investigate", "fix", "verify"]


@dataclass(frozen=True)
class IncidentInfo:
    id: str
    number: int | None
    title: str
    category: str
    severity: str
    integration_name: str
    source_system: str
    target_system: str


@dataclass(frozen=True)
class EventItem:
    view: EventView
    execution_id: str

    @property
    def strong(self) -> bool:
        """Evento de aviso ou erro prova sintoma; INFO e DEBUG só contextualizam."""
        return self.view.severity in ("WARNING", "ERROR", "CRITICAL")


@dataclass(frozen=True)
class RuleItem:
    id: str
    rule_code: str
    rule_version: str
    category: str
    description: str
    execution_id: str
    matched_event_ids: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeItem:
    id: str
    origin: Literal["tenant", "global"]
    title: str
    heading: str | None
    content: str


@dataclass(frozen=True)
class EvidenceDraft:
    kind: EvidenceKind
    ref_id: str
    label: str
    finding: str
    # Só do Evento: a chave de partição entra na FK composta.
    event_timestamp: datetime | None = None


@dataclass(frozen=True)
class HypothesisDraft:
    statement: str
    confidence: float | None


@dataclass(frozen=True)
class RecommendationDraft:
    text: str
    kind: RecommendationKind


@dataclass
class DiagnosisDraft:
    status: Status
    mode: Mode
    classification: str | None
    probable_cause: str | None
    confidence: float | None
    responsible_system: str | None
    requires_human_review: bool
    evidence: list[EvidenceDraft] = field(default_factory=list)
    hypotheses: list[HypothesisDraft] = field(default_factory=list)
    recommendations: list[RecommendationDraft] = field(default_factory=list)
    verification_notes: list[str] = field(default_factory=list)
    provider: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class Loader(Protocol):
    async def incident(self) -> IncidentInfo | None: ...

    async def correlation(self) -> Sequence[EventItem]: ...

    async def rules(self) -> Sequence[RuleItem]: ...

    async def knowledge(self, query: str) -> Sequence[KnowledgeItem]: ...
