"""Roda o `DiagnosisEngine` sobre cada caso, como o produto: as Regras do catálogo avaliam os
Eventos de cada Execução, o match mais severo é a categoria do Incidente e o motor diagnostica
no modo pedido (com o provedor e o modelo do LLMProvider, no híbrido)."""

import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from itertools import groupby

from aid_diagnosis_engine.diagnosis import (
    DiagnosisEngine,
    EventItem,
    IncidentInfo,
    KnowledgeItem,
    RuleItem,
)
from aid_diagnosis_engine.diagnosis.model import Mode
from aid_diagnosis_engine.incidents import LABELS, primary
from aid_diagnosis_engine.llm.client import GuardedLLM
from aid_diagnosis_engine.rules import evaluate
from aid_diagnosis_engine.rules.base import EventView, ExecutionView

from aid_evaluation.dataset import Case

CATEGORIES = tuple(LABELS)
# Juiz da Causa provável: (gabarito, Causa do Diagnóstico) → acertou?
Judge = Callable[[str, str], Awaitable[bool]]


@dataclass
class CaseResult:
    case_id: str
    mode: str
    expected_category: str | None
    predicted_category: str | None
    expected_inconclusive: bool
    inconclusive: bool
    probable_cause: str | None
    expected_cause: str | None
    cause_correct: bool | None
    discarded_evidence: int
    cited_evidence: int
    input_tokens: int
    output_tokens: int
    latency_ms: float
    provider: str | None
    model: str | None
    notes: list[str] = field(default_factory=list)


class CaseLoader:
    """O contexto do caso em memória, no lugar do banco (o Loader do worker)."""

    def __init__(self, incident: IncidentInfo, events: list[EventItem], rules: list[RuleItem]):
        self._incident, self._events, self._rules = incident, events, rules

    async def incident(self) -> IncidentInfo:
        return self._incident

    async def correlation(self) -> Sequence[EventItem]:
        return self._events

    async def rules(self) -> Sequence[RuleItem]:
        return self._rules

    async def knowledge(self, query: str) -> Sequence[KnowledgeItem]:
        return []


def context(case: Case) -> tuple[IncidentInfo, list[EventItem], list[RuleItem]]:
    items: list[EventItem] = []
    rules: list[RuleItem] = []
    matches = []
    ordered = sorted(case.events, key=lambda event: (event.execution_id, event.timestamp))
    for execution_id, group in groupby(ordered, key=lambda event: event.execution_id):
        events = list(group)
        views = [
            EventView(
                id=event.id,
                timestamp=event.timestamp,
                severity=event.severity,
                operation=event.operation,
                error=event.error,
                attributes=event.attributes,
            )
            for event in events
        ]
        items += [EventItem(view, execution_id) for view in views]
        execution = ExecutionView(
            id=execution_id,
            integration_id=case.integration.name,
            status="failed" if any(event.error for event in events) else "success",
            first_event_at=events[0].timestamp,
            last_event_at=events[-1].timestamp,
            evaluated_at=case.evaluated_at,
        )
        for match in evaluate(execution, views):
            matches.append(match)
            rules.append(
                RuleItem(
                    id=f"rm-{execution_id}-{match.rule_code}",
                    rule_code=match.rule_code,
                    rule_version=match.rule_version,
                    category=match.category,
                    description=str(match.details.get("description", "")),
                    execution_id=execution_id,
                    matched_event_ids=match.matched_event_ids,
                )
            )
    found = primary(matches)
    # O Incidente do match mais severo vem primeiro, como no worker.
    if found is not None:
        rules.sort(key=lambda rule: rule.rule_code != found.rule_code)
    incident = IncidentInfo(
        id=case.id,
        number=None,
        title=f"{LABELS.get(found.category, 'Falha') if found else 'Falha sem Regra'}"
        f" · {case.integration.name}",
        category=found.category if found else "UNKNOWN",
        severity=found.severity_hint if found else "medium",
        integration_name=case.integration.name,
        source_system=case.integration.source_system,
        target_system=case.integration.target_system,
    )
    return incident, sorted(items, key=lambda item: item.view.timestamp), rules


async def run_case(
    case: Case,
    mode: Mode,
    llm: GuardedLLM | None = None,
    judge: Judge | None = None,
) -> CaseResult:
    label = case.label
    if label is None:
        raise ValueError(f"caso {case.id} sem gabarito")
    incident, events, rules = context(case)
    engine = DiagnosisEngine(llm if mode == "hybrid" else None, scope="avaliacao")
    started = time.perf_counter()
    draft = await engine.run(CaseLoader(incident, events, rules), mode=mode)
    latency = (time.perf_counter() - started) * 1000
    inconclusive = draft.status == "inconclusive"
    if inconclusive:
        predicted = None
    elif draft.classification in CATEGORIES:
        predicted = draft.classification
    else:
        # O LLM classifica com um código próprio (ex.: UPSTREAM_TIMEOUT); a categoria comparável
        # é a do Incidente, que vem das Regras.
        predicted = incident.category if incident.category in CATEGORIES else None
    discarded = sum(
        1 for note in draft.verification_notes if note.startswith("Evidência descartada")
    )
    cause_correct: bool | None = None
    if judge is not None and label.probable_cause and draft.probable_cause and not inconclusive:
        cause_correct = await judge(label.probable_cause, draft.probable_cause)
    return CaseResult(
        case_id=case.id,
        mode=mode,
        expected_category=label.category,
        predicted_category=predicted,
        expected_inconclusive=label.expected_inconclusive,
        inconclusive=inconclusive,
        probable_cause=draft.probable_cause,
        expected_cause=label.probable_cause,
        cause_correct=cause_correct,
        discarded_evidence=discarded if mode == "hybrid" else 0,
        cited_evidence=(len(draft.evidence) + discarded) if mode == "hybrid" else 0,
        input_tokens=draft.input_tokens,
        output_tokens=draft.output_tokens,
        latency_ms=latency,
        provider=draft.provider,
        model=draft.model,
        notes=draft.verification_notes,
    )


async def run(
    cases: Sequence[Case],
    mode: Mode,
    llm: Callable[[], GuardedLLM] | None = None,
    judge: Judge | None = None,
) -> list[CaseResult]:
    return [
        await run_case(case, mode, llm() if llm is not None else None, judge)
        for case in cases
        if case.label is not None
    ]
