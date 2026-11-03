"""Etapa 6: nada do LLM vai para o Diagnóstico sem conferência. Evidência citada precisa ser um
dado fornecido do próprio Incidente (o contexto já vem só do tenant dele); sem nenhuma válida, o
resultado é inconclusivo; a Confiança cai com Evidência fraca ou descartada; Recomendação que
proponha ação automática é bloqueada (Recomendações são sempre ações humanas)."""

import re
from collections.abc import Sequence

from aid_diagnosis_engine.diagnosis.model import (
    DiagnosisDraft,
    EventItem,
    EvidenceDraft,
    HypothesisDraft,
    IncidentInfo,
    KnowledgeItem,
    RecommendationDraft,
    RuleItem,
    Status,
)
from aid_diagnosis_engine.diagnosis.rules_only import event_evidence, rule_evidence
from aid_diagnosis_engine.diagnosis.schema import LLMDiagnosis

DISCARD_PENALTY = 0.85
WEAK_CEILING = 0.4
REVIEW_BELOW = 0.7

AUTOMATIC = re.compile(
    r"automaticamente|autom[aá]tic[oa]|sem (interven[cç][aã]o|revis[aã]o) humana|auto-?remedia"
    r"|\b(rm\s+-rf|drop\s+table|truncate\s+table|delete\s+from|kubectl\s+delete|gcloud\s+\S+\s+delete)\b"
    r"|\b(curl|wget)\s+https?://",
    re.IGNORECASE,
)


def _ref(ref: str) -> str:
    """O `ref` veio do modelo: na nota, curto e sem quebra de linha."""
    return re.sub(r"\s+", " ", ref)[:64]


def verify(
    output: LLMDiagnosis,
    incident: IncidentInfo,
    events: Sequence[EventItem],
    rules: Sequence[RuleItem],
    knowledge: Sequence[KnowledgeItem],
) -> DiagnosisDraft:
    notes: list[str] = []
    by_event = {item.view.id: item for item in events}
    by_rule = {rule.id: rule for rule in rules}
    by_chunk = {chunk.id: chunk for chunk in knowledge}

    evidence: list[EvidenceDraft] = []
    seen: set[str] = set()
    discarded = 0
    strong = False
    for cited in output.evidence:
        ref = cited.ref.strip()
        if ref in seen:
            continue
        seen.add(ref)
        if ref in by_rule:
            evidence.append(rule_evidence(by_rule[ref], cited.finding))
            strong = True
        elif ref in by_event:
            evidence.append(event_evidence(by_event[ref], cited.finding))
            strong = strong or by_event[ref].strong
        elif ref in by_chunk:
            chunk = by_chunk[ref]
            evidence.append(
                EvidenceDraft(
                    kind="global_chunk" if chunk.origin == "global" else "chunk",
                    ref_id=chunk.id,
                    label=chunk.title[:300],
                    finding=cited.finding[:1000],
                )
            )
        else:
            discarded += 1
            notes.append(f"Evidência descartada: {_ref(ref)!r} não pertence ao Incidente.")

    status: Status = "inconclusive" if output.status == "INCONCLUSIVE" else "published"
    if not evidence:
        status = "inconclusive"
        notes.append("Nenhuma Evidência citada pelo modelo pertence ao Incidente.")

    confidence = output.confidence
    if discarded:
        confidence *= DISCARD_PENALTY
        notes.append("Confiança rebaixada: o modelo citou Evidência inexistente.")
    if evidence and not strong and confidence > WEAK_CEILING:
        confidence = WEAK_CEILING
        notes.append("Confiança rebaixada: só Evidência fraca (sem Regra nem Evento de erro).")

    responsible: str | None = output.responsible_system
    if responsible == "indeterminado":
        responsible = None
    elif responsible not in (incident.source_system, incident.target_system):
        notes.append(
            f"Sistema responsável {responsible!r} não faz parte da Integração: indeterminado."
        )
        responsible = None

    recommendations: list[RecommendationDraft] = []
    for item in output.recommendations:
        if AUTOMATIC.search(item.text):
            notes.append("Recomendação bloqueada: sugere ação automática.")
            continue
        recommendations.append(RecommendationDraft(item.text, item.kind))

    hypotheses = [
        HypothesisDraft(item.statement, round(item.confidence, 2))
        for item in sorted(output.hypotheses, key=lambda h: h.confidence, reverse=True)
    ]
    confidence = round(confidence, 2)
    return DiagnosisDraft(
        status=status,
        mode="hybrid",
        classification=output.classification,
        probable_cause=output.probable_cause,
        confidence=confidence,
        responsible_system=responsible,
        requires_human_review=(
            output.requires_human_review
            or status == "inconclusive"
            or discarded > 0
            or confidence < REVIEW_BELOW
        ),
        evidence=evidence,
        hypotheses=hypotheses,
        recommendations=recommendations,
        verification_notes=notes,
    )
