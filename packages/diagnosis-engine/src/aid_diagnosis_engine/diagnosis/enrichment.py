"""O que a consulta de leitura no destino (etapa 2, ticket #40) muda no Diagnóstico.

Depois de um timeout (ou de uma falha sem resposta clara), o risco é reenviar o que o destino já
processou. A Recomendação só muda quando a consulta foi no **destino** da Integração e o
Incidente é de uma dessas categorias; nos outros casos a consulta entra só como Evidência. A
consulta responde:
- encontrado: a primeira Recomendação passa a ser "não reenviar", e nenhuma outra sugere
  reprocessar;
- não encontrado: o reenvio não duplica, depois de corrigir a causa;
- falhou: nota de verificação, sem Evidência (não há o que provar).

Vale nos dois modos e depois do LLM: a consulta é um fato do destino, e o texto do modelo não
pode contradizê-lo. Recomendações continuam sendo ações humanas.
"""

import re
from collections.abc import Sequence

from aid_diagnosis_engine.diagnosis.model import (
    DiagnosisDraft,
    EnrichmentItem,
    EvidenceDraft,
    HypothesisDraft,
    IncidentInfo,
    RecommendationDraft,
)

SYSTEMS = {"sap": "SAP", "salesforce": "Salesforce", "gcp": "Google Cloud"}
RESEND = re.compile(r"reenvi|reprocess|reexecut|repet[ie]r? o envio", re.IGNORECASE)
MAX_RECOMMENDATIONS = 6
# Categorias em que o resultado no destino é incerto e o reenvio pode duplicar.
RESEND_RISK = {"TIMEOUT", "CONNECTIVITY", "PENDING_CONFIRMATION", "UNKNOWN"}


def system_name(item: EnrichmentItem) -> str:
    return SYSTEMS.get(item.system, item.system)


def moment(item: EnrichmentItem) -> str:
    return item.checked_at.strftime("%H:%M UTC de %d/%m")


def enrichment_evidence(item: EnrichmentItem, finding: str | None = None) -> EvidenceDraft:
    where = f"{item.entity} com {item.field} = {item.reference}"
    if item.outcome == "found":
        record = f" (registro {item.record_id}" if item.record_id else " ("
        status = f"status {item.record_status})" if item.record_status else "sem status)"
        default = f"Consulta de leitura no {system_name(item)}: {where} existe{record}{status}"
    else:
        default = f"Consulta de leitura no {system_name(item)}: {where} não existe"
    return EvidenceDraft(
        kind="enrichment",
        ref_id=item.id,
        label=f"Consulta ao {system_name(item)} · {item.entity}"[:300],
        finding=(finding or f"{default}, às {moment(item)}.")[:1000],
    )


def apply_enrichment(
    draft: DiagnosisDraft, items: Sequence[EnrichmentItem], incident: IncidentInfo
) -> DiagnosisDraft:
    decides = incident.category in RESEND_RISK
    at_target = [item for item in items if item.system == incident.target_system]
    found = [item for item in at_target if item.outcome == "found"] if decides else []
    missing = [item for item in at_target if item.outcome == "not_found"] if decides else []
    failed = [item for item in items if item.outcome == "failed"]
    cited = {e.ref_id for e in draft.evidence if e.kind == "enrichment"}
    # A consulta é o fato mais forte sobre o destino: vem antes das outras Evidências.
    answered = [item for item in items if item.outcome != "failed"]
    draft.evidence[:0] = [enrichment_evidence(item) for item in answered if item.id not in cited]
    first: list[RecommendationDraft] = []
    if found:
        item = found[0]
        first.append(
            RecommendationDraft(
                f"Não reenvie: o pedido {item.reference} já foi criado no {system_name(item)}"
                f" ({item.entity} encontrado na consulta às {moment(item)}). Confirme o registro"
                " e encerre a pendência na origem, sem reprocessar.",
                "verify",
            )
        )
        # O destino concluiu: recomendação de reenviar ou reprocessar contradiz o fato.
        draft.recommendations = [r for r in draft.recommendations if not RESEND.search(r.text)]
        draft.hypotheses.insert(
            0,
            HypothesisDraft(
                f"O {system_name(item)} concluiu a operação, mas a resposta chegou depois do"
                " timeout de quem chamou.",
                None,
            ),
        )
    elif missing:
        item = missing[0]
        first.append(
            RecommendationDraft(
                f"O pedido {item.reference} não existe no {system_name(item)} (consulta às"
                f" {moment(item)}): depois de corrigir a causa, o reenvio não duplica.",
                "verify",
            )
        )
    for item in failed:
        draft.verification_notes.append(
            f"Consulta ao {system_name(item)} indisponível: confirme manualmente se o pedido"
            f" {item.reference} existe antes de reenviar."
        )
    draft.recommendations = [*first, *draft.recommendations][:MAX_RECOMMENDATIONS]
    return draft
