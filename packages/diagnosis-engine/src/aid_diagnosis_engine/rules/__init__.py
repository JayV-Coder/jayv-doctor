from aid_diagnosis_engine.rules.base import EventView, ExecutionView, Rule, RuleMatch, Severity
from aid_diagnosis_engine.rules.catalog import RULES, RULESET_VERSION


def rule(code: str) -> Rule:
    return next(item for item in RULES if item.code == code)


def evaluate(execution: ExecutionView, events: list[EventView]) -> list[RuleMatch]:
    """Todos os matches da Execução, na ordem do catálogo."""
    return [found for item in RULES if (found := item.evaluate(execution, events)) is not None]


__all__ = [
    "RULES",
    "RULESET_VERSION",
    "EventView",
    "ExecutionView",
    "Rule",
    "RuleMatch",
    "Severity",
    "evaluate",
    "rule",
]
