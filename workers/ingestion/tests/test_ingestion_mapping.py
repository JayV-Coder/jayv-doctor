from datetime import UTC, datetime

import pytest
from aid_contracts.events import validate_event
from aid_ingestion.mapping import RejectedLineError, to_event

INTEGRATION = "00000000-0000-4000-8000-0000000001a1"
SOURCE = {"provider": "manual", "service": "importacao", "resource": "import:abc"}
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def event(record: dict[str, object]) -> dict[str, object]:
    payload = to_event(record, INTEGRATION, SOURCE, now=NOW)
    validate_event(payload)
    return payload


def test_log_do_sap_vira_evento_valido() -> None:
    payload = event(
        {
            "timestamp": "2026-11-02T14:05:00.123Z",
            "operation": "BAPI_SALESORDER_CREATEFROMDAT2",
            "severity": "E",
            "message": "Timeout ao chamar o RFC",
            "http_status": 504,
            "pedido": "[REMOVIDO:cpf]",
            "correlation_id": "abc-123",
        }
    )
    assert payload["timestamp"] == "2026-11-02T14:05:00.123000+00:00"
    assert payload["severity"] == "ERROR"
    assert payload["operation"] == "BAPI_SALESORDER_CREATEFROMDAT2"
    assert payload["execution_id"] == "abc-123"
    assert payload["error"] == {
        "category": "TIMEOUT",
        "http_status": 504,
        "message": "Timeout ao chamar o RFC",
    }
    assert payload["attributes"] == {"pedido": "[REMOVIDO:cpf]"}
    assert payload["source"] == SOURCE
    assert payload["integration_id"] == INTEGRATION


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-11-02T14:05:00-03:00", "2026-11-02T17:05:00+00:00"),
        ("2026-11-02 14:05:00", "2026-11-02T17:05:00+00:00"),
        ("02/11/2026 14:05:00", "2026-11-02T17:05:00+00:00"),
        (1793628300, "2026-11-02T14:05:00+00:00"),
        (1793628300000, "2026-11-02T14:05:00+00:00"),
    ],
    ids=["com-fuso", "sem-fuso-e-sao-paulo", "formato-brasileiro", "epoch-s", "epoch-ms"],
)
def test_formatos_de_data(raw: object, expected: str) -> None:
    assert event({"timestamp": raw, "operation": "x"})["timestamp"] == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("error", "ERROR"),
        ("ERRO", "ERROR"),
        ("A", "CRITICAL"),
        ("warn", "WARNING"),
        ("W", "WARNING"),
        ("S", "INFO"),
        ("debug", "DEBUG"),
        ("fatal", "CRITICAL"),
        ("qualquer", "INFO"),
    ],
)
def test_severidade_normalizada(raw: str, expected: str) -> None:
    assert event({"timestamp": "2026-11-02T14:05:00Z", "level": raw})["severity"] == expected


@pytest.mark.parametrize(
    ("message", "status", "category"),
    [
        ("Read timed out", None, "TIMEOUT"),
        ("token inválido", 401, "AUTH"),
        ("Too many requests", 429, "RATE_LIMIT"),
        ("campo obrigatório ausente", 422, "VALIDATION"),
        ("Pedido já existe no destino", None, "DUPLICATE"),
        ("Connection refused", None, "CONNECTIVITY"),
        ("algo estranho", 500, "UNKNOWN"),
    ],
)
def test_categoria_do_erro(message: str, status: int | None, category: str) -> None:
    record: dict[str, object] = {"timestamp": "2026-11-02T14:05:00Z", "level": "error"}
    record["message"] = message
    if status:
        record["status_code"] = status
    assert event(record)["error"]["category"] == category  # type: ignore[index]


def test_sem_data_a_linha_e_rejeitada_com_motivo() -> None:
    with pytest.raises(RejectedLineError, match="sem data"):
        to_event({"operation": "x"}, INTEGRATION, SOURCE, now=NOW)


@pytest.mark.parametrize("raw", ["1999-12-31T23:59:59Z", "2026-11-05T00:00:00Z", "ontem"])
def test_data_fora_do_intervalo_ou_ilegivel_e_rejeitada(raw: str) -> None:
    with pytest.raises(RejectedLineError, match="data"):
        to_event({"timestamp": raw}, INTEGRATION, SOURCE, now=NOW)


def test_atributos_respeitam_o_contrato() -> None:
    record: dict[str, object] = {"timestamp": "2026-11-02T14:05:00Z"}
    record.update({f"Campo Extra {index}": "v" * 300 for index in range(80)})
    record["aninhado"] = {"a": 1}
    attributes = event(record)["attributes"]
    assert isinstance(attributes, dict)
    assert len(attributes) == 64
    assert all(len(value) == 200 for value in attributes.values())
    assert "campo_extra_0" in attributes
    assert "aninhado" not in attributes


def test_operacao_padrao_quando_a_fonte_nao_informa() -> None:
    assert event({"timestamp": "2026-11-02T14:05:00Z"})["operation"] == "desconhecida"
