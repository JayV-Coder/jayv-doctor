"""Cada Regra com ao menos 3 casos positivos e 3 negativos (critério do ticket #18)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aid_diagnosis_engine.rules import RULES, RULESET_VERSION, rule
from aid_diagnosis_engine.rules.base import EventView, ExecutionView

T0 = datetime(2026, 11, 2, 14, 2, tzinfo=UTC)


def ev(
    number: int = 1,
    error: dict[str, Any] | None = None,
    attributes: dict[str, Any] | None = None,
    minutes: float = 0,
    severity: str = "ERROR",
) -> EventView:
    return EventView(
        id=f"e-{number}",
        timestamp=T0 + timedelta(minutes=minutes),
        severity=severity,
        operation="op",
        error=error,
        attributes=attributes or {},
    )


def execution(evaluated_after_minutes: float = 10) -> ExecutionView:
    return ExecutionView(
        id="x-1",
        integration_id="i-1",
        status="failed",
        first_event_at=T0,
        last_event_at=T0,
        evaluated_at=T0 + timedelta(minutes=evaluated_after_minutes),
    )


def matches(code: str, *events: EventView, evaluated_after: float = 10) -> bool:
    return rule(code).evaluate(execution(evaluated_after), list(events)) is not None


POSITIVE: dict[str, list[list[EventView]]] = {
    "INT-001": [
        [ev(error={"category": "UNKNOWN", "http_status": 401})],
        [ev(error={"category": "UNKNOWN", "http_status": 403})],
        [ev(error={"category": "AUTH"})],
    ],
    "INT-002": [
        [ev(error={"category": "UNKNOWN", "http_status": 429})],
        [ev(error={"category": "RATE_LIMIT"})],
        [ev(severity="WARNING", error={"category": "RATE_LIMIT", "http_status": 429})],
    ],
    "INT-003": [
        [ev(error={"category": "UNKNOWN", "http_status": 504})],
        [ev(error={"category": "TIMEOUT"})],
        [ev(error={"category": "CONNECTIVITY", "message": "Read timed out after 30s"})],
    ],
    "INT-004": [
        [ev(error={"category": "VALIDATION"})],
        [ev(error={"category": "UNKNOWN", "http_status": 422})],
        [ev(error={"category": "UNKNOWN", "http_status": 400})],
    ],
    "INT-005": [
        [ev(error={"category": "BUSINESS_REJECTION"})],
        # Recusa só no RETURN da BAPI, sem erro de transporte.
        [ev(error=None, attributes={"bapiret2": [{"type": "E", "id": "V1"}]}, severity="INFO")],
        [ev(error={"category": "UNKNOWN", "code": "VL 150"})],
        [ev(error={"category": "UNKNOWN", "code": "VL150"})],
    ],
    "INT-006": [
        [ev(error={"category": "DUPLICATE"})],
        [ev(error={"category": "UNKNOWN", "http_status": 409})],
        [ev(error={"category": "UNKNOWN", "message": "Pedido 4500012345 já existe"})],
    ],
    "INT-007": [
        [ev(attributes={"confirmation": "pending"}, severity="INFO")],
        [
            ev(1, attributes={"confirmation": "pending"}, severity="INFO"),
            ev(2, attributes={"confirmation": "received"}, minutes=-1, severity="INFO"),
        ],
        [ev(attributes={"confirmation": "pending"}, severity="WARNING", minutes=-30)],
    ],
    "INT-008": [
        [ev(attributes={"reconciliation": {"source_count": 10, "target_count": 9}})],
        [ev(attributes={"reconciliation": {"source_status": "OK", "target_status": "ERRO"}})],
        [
            ev(
                severity="WARNING",
                attributes={"reconciliation": {"source_count": 0, "target_count": 3}},
            )
        ],
    ],
    "INT-009": [
        [
            ev(
                error={
                    "category": "BUSINESS_REJECTION",
                    "code": "MC 601",
                    "message": "Objeto bloqueado",
                }
            )
        ],
        [
            ev(
                error={
                    "category": "BUSINESS_REJECTION",
                    "message": "Pedido 123 bloqueado pelo usuário JOAO",
                },
                attributes={"sap_message_id": "V1"},
            )
        ],
        [
            ev(
                error={
                    "category": "UNKNOWN",
                    "message": "Material is currently locked by user BATCH",
                },
                attributes={"sap_message_id": "M3"},
            )
        ],
    ],
    "INT-010": [
        [ev(error={"category": "UNKNOWN", "code": "IDOC 51"}, attributes={"idoc_status": "51"})],
        [ev(error={"category": "UNKNOWN", "code": "IDOC 51"})],
        [ev(severity="INFO", attributes={"idoc_status": "51"})],
    ],
    "INT-011": [
        [ev(error={"category": "AUTH", "code": "S# 001", "message": "Sem autorização"})],
        [
            ev(
                error={
                    "category": "BUSINESS_REJECTION",
                    "message": "No authorization for sales org 1000",
                },
                attributes={"sap_message_id": "V1"},
            )
        ],
        [
            ev(
                error={
                    "category": "UNKNOWN",
                    "message": "Usuário não tem autorização para a transação",
                },
                attributes={"sap_message_id": "00"},
            )
        ],
    ],
    "INT-012": [
        [ev(error={"category": "BUSINESS_REJECTION", "code": "M3 305"})],
        [
            ev(
                error={
                    "category": "BUSINESS_REJECTION",
                    "message": "Material 4711 not maintained in plant 1000",
                },
                attributes={"sap_message_id": "M3"},
            )
        ],
        [
            ev(
                error={"category": "UNKNOWN", "message": "Cliente 100200 não existe"},
                attributes={"sap_message_id": "VK"},
            )
        ],
    ],
}

NEGATIVE: dict[str, list[list[EventView]]] = {
    "INT-001": [
        [ev(error={"category": "UNKNOWN", "http_status": 500})],
        [ev(error=None, attributes={"http_status": 401})],
        [ev(error={"category": "RATE_LIMIT", "http_status": 429})],
    ],
    "INT-002": [
        [ev(error={"category": "UNKNOWN", "http_status": 503})],
        [ev(error={"category": "TIMEOUT"})],
        [ev(error=None, severity="INFO")],
    ],
    "INT-003": [
        [ev(error={"category": "UNKNOWN", "http_status": 502})],
        [ev(error=None, attributes={"message": "timeout configurado em 30 s"}, severity="INFO")],
        [ev(error={"category": "AUTH", "http_status": 401})],
        [ev(error={"category": "UNKNOWN", "message": "Lifetime outstanding balance invalid"})],
    ],
    "INT-004": [
        [ev(error={"category": "UNKNOWN", "http_status": 404})],
        [ev(error={"category": "AUTH", "http_status": 401})],
        [ev(error=None, severity="INFO")],
    ],
    "INT-005": [
        [
            ev(
                error={"category": "UNKNOWN"},
                attributes={"bapiret2": [{"type": "S"}, {"type": "W"}]},
            )
        ],
        [ev(error={"category": "VALIDATION", "code": "SCHEMA"})],
        [ev(error={"category": "UNKNOWN", "code": "VLAN_DOWN"})],
    ],
    "INT-006": [
        [ev(error={"category": "UNKNOWN", "http_status": 400})],
        [ev(error={"category": "UNKNOWN", "message": "Pedido criado"})],
        [ev(error=None, severity="INFO")],
    ],
    "INT-007": [
        # Confirmado depois do envio.
        [
            ev(1, attributes={"confirmation": "pending"}, severity="INFO"),
            ev(2, attributes={"confirmation": "received"}, minutes=1, severity="INFO"),
        ],
        [ev(attributes={"confirmation": "received"}, severity="INFO")],
        # Ainda dentro do prazo de confirmação.
        [ev(attributes={"confirmation": "pending"}, severity="INFO", minutes=8)],
    ],
    "INT-008": [
        [ev(attributes={"reconciliation": {"source_count": 10, "target_count": 10}})],
        [ev(attributes={"reconciliation": {"source_count": 10}})],
        [ev(attributes={"reconciliation": "10 x 9"})],
    ],
    "INT-009": [
        # Texto de bloqueio sem mensagem SAP (um 423 de API qualquer) não é bloqueio de objeto SAP.
        [ev(error={"category": "UNKNOWN", "message": "Account locked by administrator"})],
        [
            ev(
                error={"category": "BUSINESS_REJECTION", "code": "V1 801"},
                attributes={"sap_message_id": "V1"},
            )
        ],
        [
            ev(
                error=None,
                severity="INFO",
                attributes={"sap_message_id": "MC", "sap_message": "locked by user"},
            )
        ],
    ],
    "INT-010": [
        [ev(severity="INFO", attributes={"idoc_status": "53"})],
        [ev(error={"category": "UNKNOWN", "code": "IDOC 56"}, attributes={"idoc_status": "56"})],
        [ev(error={"category": "UNKNOWN", "message": "status 51"})],
    ],
    "INT-011": [
        [ev(error={"category": "AUTH", "http_status": 401, "message": "no authorization header"})],
        [
            ev(
                error={"category": "BUSINESS_REJECTION", "code": "V1 801"},
                attributes={"sap_message_id": "V1"},
            )
        ],
        [ev(error=None, severity="INFO", attributes={"sap_message_id": "S#"})],
    ],
    "INT-012": [
        [ev(error={"category": "UNKNOWN", "message": "Endpoint does not exist"})],
        [
            ev(
                error={"category": "BUSINESS_REJECTION", "code": "V1 801"},
                attributes={"sap_message_id": "V1"},
            )
        ],
        [
            ev(
                error=None,
                severity="INFO",
                attributes={"sap_message_id": "M3", "sap_message": "not maintained"},
            )
        ],
    ],
}


@pytest.mark.parametrize(
    ("code", "events"), [(code, case) for code, cases in POSITIVE.items() for case in cases]
)
def test_regra_dispara(code: str, events: list[EventView]) -> None:
    assert matches(code, *events)


@pytest.mark.parametrize(
    ("code", "events"), [(code, case) for code, cases in NEGATIVE.items() for case in cases]
)
def test_regra_nao_dispara(code: str, events: list[EventView]) -> None:
    assert not matches(code, *events)


def test_catalogo_versionado_com_metadados() -> None:
    assert RULESET_VERSION == "2026.11.1"
    assert [r.code for r in RULES] == [f"INT-{n:03d}" for n in range(1, 13)]
    for item in RULES:
        assert item.version == RULESET_VERSION
        assert item.description_pt
        assert item.severity_hint in ("low", "medium", "high", "critical")


def test_int_007_aponta_so_o_envio_sem_confirmacao() -> None:
    events = [
        ev(1, attributes={"confirmation": "pending"}, severity="INFO"),
        ev(2, attributes={"confirmation": "received"}, minutes=1, severity="INFO"),
        ev(3, attributes={"confirmation": "pending"}, minutes=2, severity="INFO"),
    ]
    found = rule("INT-007").evaluate(execution(10), events)
    assert found is not None
    assert found.matched_event_ids == ("e-3",)


def test_match_traz_versao_e_so_os_eventos_que_provam() -> None:
    events = [
        ev(1, error={"category": "UNKNOWN", "http_status": 504}),
        ev(2, error=None, severity="INFO"),
        ev(3, error={"category": "TIMEOUT"}, minutes=1),
    ]
    found = rule("INT-003").evaluate(execution(), events)
    assert found is not None
    assert found.matched_event_ids == ("e-1", "e-3")
    assert found.rule_version == "2026.11.1"
    assert found.category == "TIMEOUT"


def test_bapiret2_tipo_e_v1_abre_int_005_e_os_especificos_tem_precedencia() -> None:
    v1 = ev(
        error={
            "category": "BUSINESS_REJECTION",
            "code": "V1 801",
            "message": "Pedido bloqueado para faturamento",
        },
        attributes={"sap_message_type": "E", "sap_message_id": "V1"},
    )
    assert matches("INT-005", v1)
    lock = ev(
        error={"category": "BUSINESS_REJECTION", "code": "MC 601", "message": "Objeto bloqueado"},
        attributes={"sap_message_type": "E", "sap_message_id": "MC"},
    )
    assert matches("INT-009", lock)
    assert not matches("INT-005", lock)
