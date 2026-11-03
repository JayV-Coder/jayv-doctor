"""Tipos das Regras determinísticas (etapa 3 do motor, ADR-0003). Uma Regra classifica um
sintoma da Execução; não atribui responsabilidade."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Severity = Literal["low", "medium", "high", "critical"]
SEVERITIES: tuple[Severity, ...] = ("low", "medium", "high", "critical")


@dataclass(frozen=True)
class EventView:
    id: str
    timestamp: datetime
    severity: str
    operation: str
    error: Mapping[str, Any] | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def http_status(self) -> int | None:
        value = (self.error or {}).get("http_status")
        return value if isinstance(value, int) else None

    @property
    def category(self) -> str | None:
        value = (self.error or {}).get("category")
        return value if isinstance(value, str) else None

    @property
    def message(self) -> str:
        value = (self.error or {}).get("message")
        return value if isinstance(value, str) else ""

    @property
    def code(self) -> str:
        value = (self.error or {}).get("code")
        return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class ExecutionView:
    id: str
    integration_id: str
    status: str
    first_event_at: datetime
    last_event_at: datetime
    # Quando a avaliação acontece (o fechamento): base do "sem confirmação em X min".
    evaluated_at: datetime


@dataclass(frozen=True)
class RuleMatch:
    rule_code: str
    rule_version: str
    category: str
    severity_hint: Severity
    matched_event_ids: tuple[str, ...]
    details: Mapping[str, Any]


Selector = Callable[[EventView], bool]


@dataclass(frozen=True)
class Rule:
    """Regra como dado: o `evidence_selector` escolhe os Eventos que provam o sintoma; sem
    nenhum, não há match. `check` (opcional) olha a Execução inteira."""

    code: str
    version: str
    category: str
    severity_hint: Severity
    description_pt: str
    evidence_selector: Selector
    check: Callable[[ExecutionView, Sequence[EventView]], tuple[str, ...]] | None = None

    def evaluate(self, execution: ExecutionView, events: Sequence[EventView]) -> RuleMatch | None:
        ordered = sorted(events, key=lambda event: (event.timestamp, event.id))
        if self.check is not None:
            matched = self.check(execution, ordered)
        else:
            matched = tuple(event.id for event in ordered if self.evidence_selector(event))
        if not matched:
            return None
        return RuleMatch(
            rule_code=self.code,
            rule_version=self.version,
            category=self.category,
            severity_hint=self.severity_hint,
            matched_event_ids=matched,
            details={"description": self.description_pt, "events": len(matched)},
        )
