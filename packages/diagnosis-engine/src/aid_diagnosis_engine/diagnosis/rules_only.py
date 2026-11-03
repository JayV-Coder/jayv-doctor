"""Diagnóstico só com as Regras (etapa 3): o modo `rules_only` e o caminho quando a Cota de IA
acaba ou o LLM falha. Regra classifica sintoma; não aponta o Sistema responsável (ADR-0003)."""

from collections.abc import Sequence

from aid_diagnosis_engine.diagnosis.model import (
    DiagnosisDraft,
    EventItem,
    EvidenceDraft,
    IncidentInfo,
    Mode,
    RecommendationDraft,
    RuleItem,
    Status,
)

MAX_EVENTS_PER_RULE = 3
# Heurística (não calibrada): Regra sozinha prova o sintoma, não a causa.
RULES_CONFIDENCE = 0.5
RECURRING_CONFIDENCE = 0.6

RECOMMENDATIONS: dict[str, tuple[RecommendationDraft, ...]] = {
    "TIMEOUT": (
        RecommendationDraft(
            "Verifique a latência e o timeout configurado no sistema de destino no horário da"
            " falha.",
            "investigate",
        ),
        RecommendationDraft(
            "Confirme no destino se a operação foi concluída antes de reprocessar, para não"
            " duplicar.",
            "verify",
        ),
    ),
    "AUTH": (
        RecommendationDraft(
            "Confira a validade e as permissões da credencial usada pela integração.", "investigate"
        ),
    ),
    "RATE_LIMIT": (
        RecommendationDraft(
            "Compare o volume de chamadas com o limite do sistema de destino no período.",
            "investigate",
        ),
    ),
}
GENERIC = (
    RecommendationDraft(
        "Analise na Timeline os Eventos de erro e o que veio logo antes deles.", "investigate"
    ),
    RecommendationDraft("Confirme no sistema de destino o estado final da operação.", "verify"),
)


def event_label(item: EventItem) -> str:
    return f"{item.view.operation} · {item.view.severity}"[:300]


def event_finding(item: EventItem) -> str:
    view = item.view
    parts = [
        f"HTTP {view.http_status}" if view.http_status else "",
        view.code,
        view.message,
    ]
    text = " · ".join(part for part in parts if part)
    return (text or f"Evento {view.severity} em {view.operation}")[:1000]


def event_evidence(item: EventItem, finding: str | None = None) -> EvidenceDraft:
    return EvidenceDraft(
        kind="event",
        ref_id=item.view.id,
        label=event_label(item),
        finding=(finding or event_finding(item))[:1000],
        event_timestamp=item.view.timestamp,
    )


def rule_evidence(rule: RuleItem, finding: str | None = None) -> EvidenceDraft:
    return EvidenceDraft(
        kind="rule_match",
        ref_id=rule.id,
        label=f"{rule.rule_code} · {rule.description}"[:300],
        finding=(finding or f"A Regra {rule.rule_code} ({rule.category}) disparou na Execução.")[
            :1000
        ],
    )


def rules_draft(
    incident: IncidentInfo,
    events: Sequence[EventItem],
    rules: Sequence[RuleItem],
    *,
    mode: Mode,
    status: Status = "published",
) -> DiagnosisDraft:
    by_id = {item.view.id: item for item in events}
    evidence: list[EvidenceDraft] = []
    seen: set[str] = set()
    for rule in rules:
        evidence.append(rule_evidence(rule))
        for event_id in rule.matched_event_ids[:MAX_EVENTS_PER_RULE]:
            if event_id in by_id and event_id not in seen:
                seen.add(event_id)
                evidence.append(event_evidence(by_id[event_id]))
    if not rules:
        return DiagnosisDraft(
            status="inconclusive" if status == "published" else status,
            mode=mode,
            classification=incident.category,
            probable_cause=None,
            confidence=None,
            responsible_system=None,
            requires_human_review=True,
            recommendations=list(GENERIC),
            verification_notes=["Nenhuma Regra disparou nas Execuções do Incidente."],
        )
    executions = {rule.execution_id for rule in rules}
    main = rules[0]
    return DiagnosisDraft(
        status=status,
        mode=mode,
        classification=incident.category,
        probable_cause=(
            f"Sintoma identificado pela Regra {main.rule_code}: {main.description}"
            f" ({len(executions)} {'Execução' if len(executions) == 1 else 'Execuções'})."
        ),
        confidence=RECURRING_CONFIDENCE if len(executions) > 1 else RULES_CONFIDENCE,
        responsible_system=None,
        requires_human_review=True,
        evidence=evidence,
        recommendations=list(RECOMMENDATIONS.get(incident.category, GENERIC)),
    )
