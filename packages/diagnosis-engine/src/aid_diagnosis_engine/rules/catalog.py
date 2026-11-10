"""Regras do PRD §6, versão `2026.11.2`: a `2026.10.1`, as Regras SAP do ticket #38 e a
divergência pelo Mapa de identificadores (INT-008, ticket #40). Regra nova ou alterada ganha
versão nova do pacote; os matches antigos continuam apontando para a versão que os gerou.

Só Eventos com `error` contam para as Regras de erro (INT-001 a INT-006): um texto qualquer num
Evento INFO não abre Incidente. INT-007 e INT-008 leem convenções de `attributes`, descritas em
docs/operations/regras.md.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

from aid_diagnosis_engine.rules.base import EventView, ExecutionView, Rule

RULESET_VERSION = "2026.11.2"
# Prazo para a confirmação do destino chegar (INT-007).
CONFIRMATION_DEADLINE = timedelta(minutes=5)

TIMEOUT_TEXT = re.compile(r"\btime[d\s-]*out\b", re.IGNORECASE)
DUPLICATE_TEXT = re.compile(r"duplicat|already exists|j[áa] existe", re.IGNORECASE)
# Classes de mensagem do SAP SD/LE que indicam recusa de negócio (V1 vendas, VL remessas), com ou
# sem espaço antes do número ("VL 150", "VL150").
SAP_REJECTION = re.compile(r"^(V1|VL)(?![A-Z])", re.IGNORECASE)
# Mensagens SAP (atributos `sap_*`, preenchidos pela ingestão, #38). Códigos só os conhecidos com
# certeza; o resto pelo texto, em inglês e português.
LOCK_CODES = {"MC 601"}
LOCK_TEXT = re.compile(
    r"locked by|currently locked|being processed by (another )?user|bloquead[oa] (pelo|por)"
    r"|sendo processad[oa] (pelo|por)",
    re.IGNORECASE,
)
AUTHORIZATION_TEXT = re.compile(
    r"no authori[sz]ation|not authori[sz]ed|sem autoriza|n[ãa]o (tem|possui) autoriza",
    re.IGNORECASE,
)
MASTER_DATA_CODES = {"M3 305"}
MASTER_DATA_TEXT = re.compile(
    r"not maintained|does not exist|is not defined|n[ãa]o (est[áa] )?mantid|n[ãa]o existe"
    r"|n[ãa]o (est[áa] )?definid",
    re.IGNORECASE,
)


def failed(event: EventView) -> bool:
    return event.error is not None


def auth(event: EventView) -> bool:
    # Falta de autorização SAP tem Regra própria (INT-011), mesmo vinda num HTTP 403.
    return (
        failed(event)
        and (event.category == "AUTH" or event.http_status in (401, 403))
        and not sap_specific(event)
    )


def rate_limit(event: EventView) -> bool:
    return failed(event) and (event.category == "RATE_LIMIT" or event.http_status == 429)


def timeout(event: EventView) -> bool:
    return failed(event) and (
        event.category == "TIMEOUT"
        or event.http_status == 504
        or bool(TIMEOUT_TEXT.search(event.message))
    )


def validation(event: EventView) -> bool:
    # O SAP Gateway devolve bloqueio e cadastro faltante como HTTP 400: as Regras SAP vencem.
    return (
        failed(event)
        and (event.category == "VALIDATION" or event.http_status in (400, 422))
        and not sap_specific(event)
    )


def bapi_rejected(attributes: Mapping[str, Any]) -> bool:
    """BAPIRET2 (`bapiret2` ou `bapi_return`, lista ou item) com alguma linha tipo E ou A."""
    for key in ("bapiret2", "bapi_return"):
        value = attributes.get(key)
        lines = value if isinstance(value, list) else [value]
        if any(isinstance(line, Mapping) and line.get("type") in ("E", "A") for line in lines):
            return True
    return False


def sap(event: EventView) -> bool:
    """Evento com mensagem SAP reconhecida pela ingestão (BAPIRET2, OData, SLG1…)."""
    return bool(event.attributes.get("sap_message_id"))


def object_locked(event: EventView) -> bool:
    return failed(event) and (
        event.code.upper() in LOCK_CODES or (sap(event) and bool(LOCK_TEXT.search(event.message)))
    )


def idoc_failed(event: EventView) -> bool:
    return failed(event) and (
        str(event.attributes.get("idoc_status", "")) == "51" or event.code.upper() == "IDOC 51"
    )


def sap_authorization(event: EventView) -> bool:
    return failed(event) and (
        event.code.upper().startswith("S#")
        or str(event.attributes.get("sap_message_id", "")).upper().startswith("S#")
        or (sap(event) and bool(AUTHORIZATION_TEXT.search(event.message)))
    )


def master_data_missing(event: EventView) -> bool:
    return failed(event) and (
        event.code.upper() in MASTER_DATA_CODES
        or (sap(event) and bool(MASTER_DATA_TEXT.search(event.message)))
    )


def sap_specific(event: EventView) -> bool:
    """Sintomas SAP com Regra própria: a recusa genérica (INT-005) não os disputa."""
    return (
        object_locked(event)
        or idoc_failed(event)
        or sap_authorization(event)
        or master_data_missing(event)
    )


def business_rejection(event: EventView) -> bool:
    if sap_specific(event):
        return False
    # A BAPI responde sem erro de transporte e a recusa vem só no RETURN: o BAPIRET2 basta, e
    # também a mensagem SAP tipo E/A que a ingestão reconheceu (#38).
    if str(event.attributes.get("sap_message_type", "")).upper() in ("E", "A") and failed(event):
        return True
    return bapi_rejected(event.attributes) or (
        failed(event)
        and (event.category == "BUSINESS_REJECTION" or bool(SAP_REJECTION.match(event.code)))
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
    """Envios (`confirmation = pending`) depois da última confirmação, já fora do prazo. Só eles
    são a Evidência: um envio anterior, já confirmado, não prova nada."""
    confirmed = [e.timestamp for e in events if confirmation(e) in ("received", "confirmed")]
    since = max(confirmed) if confirmed else None
    sent = [
        event
        for event in events
        if confirmation(event) == "pending" and (since is None or event.timestamp > since)
    ]
    if not sent or execution.evaluated_at - sent[-1].timestamp < CONFIRMATION_DEADLINE:
        return ()
    return tuple(event.id for event in sent)


def divergence(execution: ExecutionView, events: Sequence[EventView]) -> tuple[str, ...]:
    """Contagem ou status divergentes em `attributes.reconciliation`, ou a chave do Mapa vista na
    origem e ausente no destino (`execution.unreconciled`, #40)."""
    unreconciled = set(execution.unreconciled)
    return tuple(event.id for event in events if divergent(event) or event.id in unreconciled)


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
        "Origem e destino divergem em contagem ou status, ou o registro da origem não chegou"
        " ao destino.",
        divergent,
        check=divergence,
    ),
    Rule(
        "INT-009",
        RULESET_VERSION,
        "SAP_LOCK",
        "medium",
        "O objeto estava bloqueado por outro usuário no SAP (ex.: MC 601); tende a passar numa"
        " nova tentativa.",
        object_locked,
    ),
    Rule(
        "INT-010",
        RULESET_VERSION,
        "IDOC_ERROR",
        "high",
        "IDoc com status 51: o documento de aplicação não foi lançado no SAP.",
        idoc_failed,
    ),
    Rule(
        "INT-011",
        RULESET_VERSION,
        "SAP_AUTHORIZATION",
        "high",
        "O usuário técnico não tem autorização no SAP para a operação.",
        sap_authorization,
    ),
    Rule(
        "INT-012",
        RULESET_VERSION,
        "MASTER_DATA",
        "medium",
        "Cadastro mestre faltante ou incompleto no SAP (ex.: material não mantido no centro,"
        " M3 305).",
        master_data_missing,
    ),
)
