"""Do match ao Incidente: qual categoria abre o Incidente e com que severidade.

Severidade inicial = dica da Regra, um nível acima em produção, e crítica a partir de 20
Execuções no mesmo Incidente (ticket #18)."""

from collections.abc import Sequence

from aid_diagnosis_engine.rules.base import SEVERITIES, RuleMatch, Severity

CRITICAL_VOLUME = 20


def incident_severity(hint: Severity, environment: str, executions: int) -> Severity:
    if executions >= CRITICAL_VOLUME:
        return "critical"
    level = SEVERITIES.index(hint) + (1 if environment == "prd" else 0)
    return SEVERITIES[min(level, len(SEVERITIES) - 1)]


def primary(matches: Sequence[RuleMatch]) -> RuleMatch | None:
    """Uma Execução entra em um Incidente só: o do match mais severo (empate: ordem do catálogo,
    que é a ordem de `matches`)."""
    if not matches:
        return None
    ranked = sorted(
        enumerate(matches), key=lambda item: (-SEVERITIES.index(item[1].severity_hint), item[0])
    )
    return ranked[0][1]


LABELS = {
    "AUTH": "Falha de autenticação",
    "RATE_LIMIT": "Limite de chamadas",
    "TIMEOUT": "Timeout",
    "VALIDATION": "Payload recusado na validação",
    "BUSINESS_REJECTION": "Rejeição de negócio",
    "DUPLICATE": "Registro duplicado",
    "PENDING_CONFIRMATION": "Envio sem confirmação",
    "DIVERGENCE": "Divergência entre origem e destino",
}


def incident_title(category: str, integration: str) -> str:
    return f"{LABELS.get(category, category)} · {integration}"[:200]
