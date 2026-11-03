"""Casos sintéticos do dataset v1, baseados nas Regras INT-001 a INT-008, mais casos sem causa
identificável e casos com dois sinais. Determinístico pela semente: o mesmo comando gera o mesmo
arquivo. Eventos sem dado pessoal (ids e pedidos fictícios)."""

import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from aid_evaluation.dataset import Case, CaseEvent, Integration, Label, Source, System

T0 = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
INTEGRATIONS: list[tuple[str, System, System]] = [
    ("Pedidos Salesforce → SAP", "salesforce", "sap"),
    ("Notas SAP → BigQuery", "sap", "gcp"),
    ("Leads GCP → Salesforce", "gcp", "salesforce"),
    ("Clientes Salesforce → GCP", "salesforce", "gcp"),
]
NAMES = {"sap": "SAP", "salesforce": "Salesforce", "gcp": "Google Cloud", "other": "destino"}
OPERATIONS = {
    "sap": ["BAPI_SALESORDER_CREATE", "BAPI_CUSTOMER_CREATE", "IDOC_INBOUND_ORDERS"],
    "salesforce": ["sobjects/Account", "composite/sobjects", "sobjects/Lead"],
    "gcp": ["bigquery.insertAll", "pubsub.publish", "storage.objects.insert"],
    "other": ["POST /api"],
}

Built = tuple[list[dict[str, Any]], Label]
Builder = Callable[[random.Random, str, System, System, datetime], Built]


def _label(category: str | None, cause: str | None, system: System | None) -> Label:
    return Label(
        category=category,
        probable_cause=cause,
        responsible_system=system,
        expected_inconclusive=category is None,
        labeled_by="sintético",
    )


def _prelude(rng: random.Random, start: datetime, source: System) -> list[dict[str, Any]]:
    steps = rng.randint(1, 3)
    return [
        {
            "severity": "INFO",
            "operation": rng.choice(["outbound_message", "transform", "enqueue", "mapping"]),
            "at": start + timedelta(milliseconds=120 * index),
            "attributes": {"step": index, "source": source},
        }
        for index in range(steps)
    ]


def _error(
    rng: random.Random, target: System, start: datetime, error: dict[str, Any], **attributes: Any
) -> dict[str, Any]:
    return {
        "severity": "ERROR",
        "operation": rng.choice(OPERATIONS[target]),
        "at": start + timedelta(seconds=rng.randint(1, 35)),
        "error": error,
        "attributes": attributes,
    }


def auth(rng: random.Random, name: str, source: System, target: System, start: datetime) -> Built:
    status = rng.choice([401, 403])
    message = rng.choice(["invalid_grant", "INVALID_SESSION_ID", "Forbidden", "token expired"])
    category = rng.choice(["AUTH", "UNKNOWN"])
    events = [
        *_prelude(rng, start, source),
        _error(
            rng, target, start, {"http_status": status, "message": message, "category": category}
        ),
    ]
    cause = (
        f"A credencial usada pela integração foi recusada pelo {NAMES[target]}: token expirado ou"
        " sem permissão para a operação."
    )
    return events, _label("AUTH", cause, source)


def rate_limit(
    rng: random.Random, name: str, source: System, target: System, start: datetime
) -> Built:
    events = _prelude(rng, start, source)
    for burst in range(rng.randint(1, 3)):
        events.append(
            _error(
                rng,
                target,
                start + timedelta(seconds=burst),
                {
                    "http_status": 429,
                    "message": rng.choice(["Too Many Requests", "REQUEST_LIMIT_EXCEEDED"]),
                },
                retry_after=rng.choice([30, 60, 120]),
            )
        )
    cause = f"O limite de chamadas do {NAMES[target]} foi atingido no horário de pico da carga."
    return events, _label("RATE_LIMIT", cause, target)


def timeout(
    rng: random.Random, name: str, source: System, target: System, start: datetime
) -> Built:
    variant = rng.choice(["504", "text", "category"])
    variants: dict[str, dict[str, Any]] = {
        "504": {"http_status": 504, "message": "UPSTREAM_TIMEOUT"},
        "text": {"message": f"Read timed out after {rng.choice([30, 60])}s", "category": "UNKNOWN"},
        "category": {"category": "TIMEOUT", "message": "deadline exceeded"},
    }
    error = variants[variant]
    events = [
        *_prelude(rng, start, source),
        _error(rng, target, start, error, duration_ms=rng.choice([30000, 60000])),
    ]
    cause = f"O {NAMES[target]} não respondeu dentro do timeout configurado na chamada."
    return events, _label("TIMEOUT", cause, target)


def validation(
    rng: random.Random, name: str, source: System, target: System, start: datetime
) -> Built:
    field = rng.choice(["CustomerNumber", "Email", "Amount", "ShipToParty"])
    events = [
        *_prelude(rng, start, source),
        _error(
            rng,
            target,
            start,
            {"http_status": rng.choice([400, 422]), "message": f"Required field missing: {field}"},
        ),
    ]
    cause = (
        f"O payload foi enviado sem o campo obrigatório {field} e o destino recusou na validação."
    )
    return events, _label("VALIDATION", cause, source)


def business_rejection(
    rng: random.Random, name: str, source: System, target: System, start: datetime
) -> Built:
    code, text = rng.choice(
        [
            ("V1 154", "Cliente bloqueado para pedidos de venda"),
            ("VL 150", "Material não disponível para a data de remessa"),
            ("V1 320", "Limite de crédito excedido"),
        ]
    )
    with_transport_error = rng.random() < 0.5
    attributes = {
        "bapiret2": [
            {"type": "E", "id": code.split()[0], "number": code.split()[1], "message": text}
        ]
    }
    if with_transport_error:
        last = _error(
            rng,
            "sap",
            start,
            {"code": code.replace(" ", ""), "message": text, "category": "UNKNOWN"},
            **attributes,
        )
    else:
        last = {
            "severity": "WARNING",
            "operation": "BAPI_SALESORDER_CREATE",
            "at": start + timedelta(seconds=rng.randint(1, 10)),
            "attributes": attributes,
        }
    events = [*_prelude(rng, start, source), last]
    cause = f"O SAP recusou a operação por regra de negócio: {text.lower()}."
    return events, _label("BUSINESS_REJECTION", cause, "sap")


def duplicate(
    rng: random.Random, name: str, source: System, target: System, start: datetime
) -> Built:
    options: list[dict[str, Any]] = [
        {"http_status": 409, "message": "Conflict"},
        {"message": "DUPLICATE_VALUE: duplicate value found", "category": "UNKNOWN"},
        {"category": "DUPLICATE", "message": "registro já existe"},
    ]
    error = rng.choice(options)
    events = [*_prelude(rng, start, source), _error(rng, target, start, error)]
    cause = (
        "A integração reenviou um registro que já existe no destino (reprocessamento sem"
        " idempotência)."
    )
    return events, _label("DUPLICATE", cause, source)


def pending(
    rng: random.Random, name: str, source: System, target: System, start: datetime
) -> Built:
    events = [
        *_prelude(rng, start, source),
        {
            "severity": "INFO",
            "operation": rng.choice(OPERATIONS[target]),
            "at": start + timedelta(seconds=2),
            "attributes": {"confirmation": "pending"},
        },
    ]
    cause = f"O envio saiu, mas o {NAMES[target]} não confirmou o recebimento dentro do prazo."
    return events, _label("PENDING_CONFIRMATION", cause, target)


def divergence(
    rng: random.Random, name: str, source: System, target: System, start: datetime
) -> Built:
    sent = rng.randint(100, 5000)
    received = sent - rng.randint(1, 50)
    events = [
        *_prelude(rng, start, source),
        {
            "severity": "WARNING",
            "operation": "reconciliation",
            "at": start + timedelta(seconds=5),
            "attributes": {"reconciliation": {"source_count": sent, "target_count": received}},
        },
    ]
    cause = (
        f"O {NAMES[target]} recebeu menos registros do que a origem enviou ({received} de {sent})."
    )
    return events, _label("DIVERGENCE", cause, target)


def no_cause(
    rng: random.Random, name: str, source: System, target: System, start: datetime
) -> Built:
    variant = rng.choice(["500", "info_only", "unknown"])
    if variant == "info_only":
        return _prelude(rng, start, source), _label(None, None, None)
    error = (
        {"http_status": 500, "message": "Internal Server Error"}
        if variant == "500"
        else {
            "message": rng.choice(["Unexpected error", "Erro desconhecido", "NullPointerException"])
        }
    )
    return [*_prelude(rng, start, source), _error(rng, target, start, error)], _label(
        None, None, None
    )


def mixed(rng: random.Random, name: str, source: System, target: System, start: datetime) -> Built:
    """Autenticação recusada e, na retentativa, timeout: o Incidente é o da autenticação (mesma
    severidade, primeira no catálogo)."""
    events = [
        *_prelude(rng, start, source),
        _error(rng, target, start, {"http_status": 401, "message": "invalid_grant"}),
        _error(
            rng,
            target,
            start + timedelta(seconds=40),
            {"http_status": 504, "message": "UPSTREAM_TIMEOUT"},
        ),
    ]
    cause = (
        f"A credencial foi recusada pelo {NAMES[target]}; o timeout seguinte é efeito das"
        " retentativas."
    )
    return events, _label("AUTH", cause, source)


SCENARIOS: list[tuple[str, str | None, Builder, int]] = [
    ("auth", "INT-001", auth, 13),
    ("rate-limit", "INT-002", rate_limit, 13),
    ("timeout", "INT-003", timeout, 13),
    ("validation", "INT-004", validation, 13),
    ("business-rejection", "INT-005", business_rejection, 13),
    ("duplicate", "INT-006", duplicate, 13),
    ("pending", "INT-007", pending, 13),
    ("divergence", "INT-008", divergence, 13),
    ("no-cause", None, no_cause, 18),
    ("mixed", "INT-001", mixed, 4),
]


def generate(seed: int = 30) -> list[Case]:
    rng = random.Random(seed)  # noqa: S311 - dado de teste, não segredo
    cases: list[Case] = []
    for scenario, rule, builder, count in SCENARIOS:
        for index in range(count):
            name, source, target = rng.choice(INTEGRATIONS)
            if scenario == "business-rejection":
                name, source, target = INTEGRATIONS[0]
            start = T0 + timedelta(days=len(cases), minutes=rng.randint(0, 600))
            raw, label = builder(rng, name, source, target, start)
            execution = f"exec-{scenario}-{index:02d}"
            events = [
                CaseEvent(
                    id=f"evt-{scenario}-{index:02d}-{position}",
                    execution_id=execution,
                    timestamp=item["at"],
                    severity=item["severity"],
                    operation=item["operation"],
                    error=item.get("error"),
                    attributes=item.get("attributes", {}),
                )
                for position, item in enumerate(raw)
            ]
            cases.append(
                Case(
                    id=f"syn-{scenario}-{index:02d}",
                    source=Source(kind="synthetic", rule=rule, scenario=scenario),
                    integration=Integration(name=name, source_system=source, target_system=target),
                    events=events,
                    evaluated_at=max(event.timestamp for event in events) + timedelta(minutes=10),
                    label=label,
                )
            )
    return cases
