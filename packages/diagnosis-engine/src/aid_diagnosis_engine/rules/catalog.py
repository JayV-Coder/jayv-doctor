"""Regras iniciais (PRD §6), versão `2026.10.1`. Regra nova ou alterada ganha versão nova do
pacote; os matches antigos continuam apontando para a versão que os gerou.

Só Eventos com `error` contam para as Regras de erro (INT-001 a INT-006): um texto qualquer num
Evento INFO não abre Incidente. INT-007 e INT-008 leem convenções de `attributes`, descritas em
docs/operations/regras.md.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

from aid_diagnosis_engine.rules.base import EventView, ExecutionView, Rule

RULESET_VERSION = "2026.10.1"
# Prazo para a confirmação do destino chegar (INT-007).
CONFIRMATION_DEADLINE = timedelta(minutes=5)

TIMEOUT_TEXT = re.compile(r"time[d\s-]*out", re.IGNORECASE)
DUPLICATE_TEXT = re.compile(r"duplicat|already exists|j[áa] existe", re.IGNORECASE)
# Classes de mensagem do SAP SD/LE que indicam recusa de negócio (V1 vendas, VL remessas).
SAP_REJECTION = re.compile(r"^(V1|VL)\b", re.IGNORECASE)


def failed(event: EventView) -> bool:
    return event.error is not None


def auth(event: EventView) -> bool:
    return failed(event) and (event.category == "AUTH" or event.http_status in (401, 403))


def rate_limit(event: EventView) -> bool:
    return failed(event) and (event.category == "RATE_LIMIT" or event.http_status == 429)


def timeout(event: EventView) -> bool:
    return failed(event) and (
        event.category == "TIMEOUT"
        or event.http_status == 504
        or bool(TIMEOUT_TEXT.search(event.message))
    )


def validation(event: EventView) -> bool:
    return failed(event) and (event.category == "VALIDATION" or event.http_status in (400, 422))


def bapi_rejected(attributes: Mapping[str, Any]) -> bool:
    """BAPIRET2 (`bapiret2` ou `bapi_return`, lista ou item) com alguma linha tipo E ou A."""
    for key in ("bapiret2", "bapi_return"):
        value = attributes.get(key)
        lines = value if isinstance(value, list) else [value]
        if any(isinstance(line, Mapping) and line.get("type") in ("E", "A") for line in lines):
            return True
    return False


def business_rejection(event: EventView) -> bool:
    return failed(event) and (
        event.category == "BUSINESS_REJECTION"
        or bapi_rejected(event.attributes)
        or bool(SAP_REJECTION.match(event.code))
    )


def duplicate(event: EventView) -> bool:
    return failed(event) and (
        event.category == "DUPLICATE"
        or event.http_status == 409
        or bool(DUPLICATE_TEXT.search(event.message))
    )


def confirmation(event: EventView) -> str | None:
    value = event.attributes.get("confirmation")
    return value if isinstance(value, str) else None


def unconfirmed(execution: ExecutionView, events: Sequence[EventView]) -> tuple[str, ...]:
    """Envios (`confirmation = pending`) sem confirmação posterior, já fora do prazo."""
    sent = [event for event in events if confirmation(event) == "pending"]
    if not sent:
        return ()
    last = sent[-1]
    confirmed = any(
        confirmation(event) in ("received", "confirmed") and event.timestamp >= last.timestamp
        for event in events
    )
    if confirmed or execution.evaluated_at - last.timestamp < CONFIRMATION_DEADLINE:
        return ()
    return tuple(event.id for event in sent)


def divergent(event: EventView) -> bool:
    """`attributes.reconciliation` com contagens ou status de origem e destino diferentes."""
    found = event.attributes.get("reconciliation")
    if not isinstance(found, Mapping):
        return False
    for kind in ("count", "status"):
        source, target = found.get(f"source_{kind}"), found.get(f"target_{kind}")
        if source is not None and target is not None and source != target:
            return True
    return False


RULES: tuple[Rule, ...] = (
    Rule(
        "INT-001",
        RULESET_VERSION,
        "AUTH",
        "high",
        "O destino recusou a autenticação ou a autorização (HTTP 401/403).",
        auth,
    ),
    Rule(
        "INT-002",
        RULESET_VERSION,
        "RATE_LIMIT",
        "medium",
        "O destino limitou as chamadas (HTTP 429).",
        rate_limit,
    ),
    Rule(
        "INT-003",
        RULESET_VERSION,
        "TIMEOUT",
        "high",
        "Tempo esgotado (HTTP 504 ou timeout): o resultado no destino é indeterminado.",
        timeout,
    ),
    Rule(
        "INT-004",
        RULESET_VERSION,
        "VALIDATION",
        "medium",
        "O payload foi recusado na validação (HTTP 400/422).",
        validation,
    ),
    Rule(
        "INT-005",
        RULESET_VERSION,
        "BUSINESS_REJECTION",
        "high",
        "O SAP rejeitou por regra de negócio (BAPIRET2 tipo E/A, mensagens V1/VL).",
        business_rejection,
    ),
    Rule(
        "INT-006",
        RULESET_VERSION,
        "DUPLICATE",
        "low",
        "O identificador já existe no destino (duplicidade).",
        duplicate,
    ),
    Rule(
        "INT-007",
        RULESET_VERSION,
        "PENDING_CONFIRMATION",
        "medium",
        "Enviado, sem confirmação do destino dentro do prazo.",
        lambda event: confirmation(event) == "pending",
        check=unconfirmed,
    ),
    Rule(
        "INT-008",
        RULESET_VERSION,
        "DIVERGENCE",
        "high",
        "Origem e destino divergem em contagem ou status.",
        divergent,
    ),
)
