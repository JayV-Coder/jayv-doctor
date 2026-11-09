"""Respostas SAP nos Eventos e exportações da SM58, SLG1 e IDoc (ticket #38, fase A)."""

import json
from datetime import UTC, datetime
from typing import Any

from aid_contracts.events import validate_event
from aid_ingestion.cleaning import EventSanitizer
from aid_ingestion.mapping import to_event
from aid_ingestion.sap import enrich, parse

INTEGRATION = "00000000-0000-4000-8000-0000000001a1"
TENANT = "00000000-0000-4000-8000-00000000ac01"
NOW = datetime(2026, 11, 10, 18, 0, tzinfo=UTC)
SOURCE = {"provider": "sap", "service": "ECC"}


def event(**changes: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "event_id": "0192e1c4-7b2c-7d4e-8f00-123456789abc",
        "integration_id": INTEGRATION,
        "timestamp": "2026-11-10T14:05:00Z",
        "source": SOURCE,
        "operation": "BAPI_SALESORDER_CREATEFROMDAT2",
        "severity": "INFO",
        **changes,
    }


def test_bapiret2_tipo_e_vira_erro_com_o_codigo_sap() -> None:
    body = json.dumps(
        {
            "RETURN": [
                {"TYPE": "S", "ID": "V4", "NUMBER": "233", "MESSAGE": "SALES_HEADER_IN processado"},
                {
                    "TYPE": "E",
                    "ID": "V1",
                    "NUMBER": "801",
                    "MESSAGE": "Pedido do cliente bloqueado",
                },
            ]
        }
    )
    enriched = enrich(event(attributes={"response": body}))
    assert enriched["severity"] == "ERROR"
    assert enriched["error"] == {
        "category": "BUSINESS_REJECTION",
        "code": "V1 801",
        "message": "Pedido do cliente bloqueado",
    }
    assert enriched["attributes"]["sap_message_type"] == "E"
    validate_event(enriched)


def test_odata_v2_com_errordetails_e_v4() -> None:
    v2 = {
        "error": {
            "code": "MC/601",
            "message": {"lang": "pt", "value": "Objeto bloqueado pelo usuário"},
            "innererror": {
                "errordetails": [
                    {
                        "code": "MC/601",
                        "message": "Objeto bloqueado pelo usuário",
                        "severity": "error",
                    }
                ]
            },
        }
    }
    found = parse(json.dumps(v2))
    assert [m.code for m in found] == ["MC 601"]
    v4 = {
        "error": {
            "code": "/IWBEP/CM_MGW_RT/022",
            "message": "Recurso não encontrado",
            "details": [],
        }
    }
    assert parse(json.dumps(v4))[0].code == "/IWBEP/CM_MGW_RT 022"


def test_soap_fault_do_pi_po() -> None:
    fault = (
        '<SOAP:Envelope xmlns:SOAP="http://schemas.xmlsoap.org/soap/envelope/"><SOAP:Body>'
        "<SOAP:Fault><faultcode>SOAP:Server</faultcode><faultstring>Server Error</faultstring>"
        '<detail><s:SystemError xmlns:s="http://sap.com/xi/WebService/xi2.0">'
        "<context>XIAdapter</context><code>ADAPTER.JAVA_EXCEPTION</code>"
        "<text>Receiver channel timed out</text></s:SystemError></detail></SOAP:Fault>"
        "</SOAP:Body></SOAP:Envelope>"
    )
    enriched = enrich(event(severity="ERROR", error={"category": "UNKNOWN", "message": fault}))
    assert (
        enriched["attributes"]["sap_message"]
        == "ADAPTER.JAVA_EXCEPTION: Receiver channel timed out"
    )
    # O código do PI não é uma mensagem de classe e número: não vira error.code.
    assert "code" not in enriched["error"]


def test_texto_comum_e_xml_com_entidade_nao_mudam_o_evento() -> None:
    plain = event(severity="ERROR", error={"category": "TIMEOUT", "message": "Read timed out"})
    assert enrich(plain) == plain
    bomb = '<!DOCTYPE x [<!ENTITY a "aaaa">]><Fault>&a;</Fault>'
    assert parse(bomb) == []


def test_codigo_existente_nao_e_sobrescrito() -> None:
    body = json.dumps(
        {"TYPE": "E", "ID": "M3", "NUMBER": "305", "MESSAGE": "Material não mantido no centro"}
    )
    enriched = enrich(
        event(severity="ERROR", error={"category": "VALIDATION", "code": "E-42", "message": body})
    )
    assert enriched["error"]["code"] == "E-42"
    assert enriched["error"]["category"] == "VALIDATION"
    assert enriched["attributes"]["sap_message_id"] == "M3"


def test_exportacao_sm58() -> None:
    record = {
        "Caller": "RFCUSER",
        "Function Module": "IDOC_INBOUND_ASYNCHRONOUS",
        "Target System": "PRDCLNT100",
        "Date": "10.11.2026",
        "Time": "14:05:00",
        "Status Text": "Name or password is incorrect",
        "Transaction ID": "0A0B0C0D0E0F1234",
    }
    mapped = to_event(record, INTEGRATION, SOURCE, now=NOW)
    assert mapped["operation"] == "IDOC_INBOUND_ASYNCHRONOUS"
    assert mapped["execution_id"] == "0A0B0C0D0E0F1234"
    assert mapped["severity"] == "ERROR"
    assert mapped["attributes"]["sap_export"] == "SM58"
    validate_event(mapped)


def test_exportacao_slg1_com_codigo_de_classe_e_numero() -> None:
    record = {
        "Date": "10.11.2026",
        "Time": "14:05:00",
        "User": "BATCH",
        "Object": "/SCWM/WME",
        "Subobject": "DLV",
        "External ID": "80001234",
        "Message Type": "E",
        "Message Class": "M7",
        "Message Number": "21",
        "Message Text": "Saldo insuficiente no estoque de utilização livre",
    }
    mapped = to_event(record, INTEGRATION, SOURCE, now=NOW)
    assert mapped["error"]["code"] == "M7 021"
    assert mapped["operation"] == "/SCWM/WME/DLV"
    assert mapped["attributes"]["sap_message_type"] == "E"
    validate_event(mapped)


def test_status_de_idoc_51_e_53() -> None:
    failed = {
        "IDoc number": "0000000000123456",
        "Status": "51",
        "Status text": "Documento de aplicação não lançado",
        "Message Type": "ORDERS",
        "Created on": "10.11.2026",
        "Time created": "14:05:00",
    }
    mapped = to_event(failed, INTEGRATION, SOURCE, now=NOW)
    assert (mapped["severity"], mapped["error"]["code"], mapped["attributes"]["idoc_status"]) == (
        "ERROR",
        "IDOC 51",
        "51",
    )
    posted = {**failed, "Status": "53", "Status text": "Documento de aplicação lançado"}
    assert to_event(posted, INTEGRATION, SOURCE, now=NOW)["severity"] == "INFO"


def test_sanitizacao_aplica_o_enriquecimento_em_todo_caminho() -> None:
    body = json.dumps({"TYPE": "E", "ID": "V1", "NUMBER": "801", "MESSAGE": "Pedido bloqueado"})
    cleaned, _ = EventSanitizer(b"0" * 32, TENANT)(event(attributes={"response": body}))
    assert cleaned["error"]["code"] == "V1 801"
    validate_event(cleaned)
