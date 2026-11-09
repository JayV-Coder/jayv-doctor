"""Respostas SAP dentro dos Eventos (ticket #38, fase A).

- **Parsers:** BAPIRET2 (`TYPE`, `ID`, `NUMBER`, `MESSAGE`), erro OData v2/v4 (`error.code`,
  `innererror.errordetails`, `details`) e SOAP Fault do PI/PO, achados na mensagem do erro ou
  num atributo de texto.
- **Normalização:** `error.code = "<ID> <NUMBER>"` (ex.: `V1 801`), e os atributos planos
  `sap_message_type`, `sap_message_id`, `sap_message_number` e `sap_message`, que as Regras
  INT-005 e INT-009 a INT-012 leem. Uma BAPI que responde 200 com RETURN tipo E vira erro.
- **Presets de importação:** linhas exportadas da SM58 (tRFC), da SLG1 (log de aplicação) e da
  lista de status de IDoc viram registros no formato que `mapping.to_event` entende.
"""

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

SEVERITY = {"A": 5, "X": 5, "E": 4, "W": 3, "S": 1, "I": 1}
MESSAGE_CLASS = re.compile(r"^[A-Z0-9/#_]{1,20}$", re.IGNORECASE)
NUMBER = re.compile(r"^\d{1,3}$")
ODATA_CODE = re.compile(r"^([A-Z0-9/#_]{1,20})/(\d{1,3})$", re.IGNORECASE)
MAX_TEXT = 200
# Limites do contrato: o enriquecimento não pode tirar o Evento dele.
MAX_ATTRIBUTES = 64
MAX_XML = 64 * 1024
UNSAFE_XML = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


@dataclass(frozen=True)
class SapMessage:
    type: str
    id: str
    number: str
    text: str

    @property
    def code(self) -> str:
        return f"{self.id.upper()} {self.number.zfill(3)}"


def lower_keys(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).lower(): item for key, item in value.items()}


def from_bapiret2(value: Any) -> list[SapMessage]:
    """Item ou lista no formato BAPIRET2 (ou o RETURN de uma BAPI), em qualquer caixa."""
    items = value if isinstance(value, list) else [value]
    found = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        row = lower_keys(item)
        kind, klass, number = (str(row.get(k, "")).strip() for k in ("type", "id", "number"))
        if kind.upper() in SEVERITY and MESSAGE_CLASS.match(klass) and NUMBER.match(number):
            found.append(
                SapMessage(kind.upper(), klass, number, str(row.get("message", ""))[:MAX_TEXT])
            )
    return found


def from_odata(error: Mapping[str, Any]) -> list[SapMessage]:
    """`{"error": {"code": "V1/801", "message": …, "innererror": {"errordetails": […]}}}` (v2) ou
    `{"error": {"code", "message", "details": […]}}` (v4)."""
    found = []
    details: Any = []
    inner = error.get("innererror")
    if isinstance(inner, Mapping):
        details = inner.get("errordetails") or []
    details = details or error.get("details") or []
    for item in [error, *(d for d in details if isinstance(d, Mapping))]:
        match = ODATA_CODE.match(str(item.get("code", "")))
        if not match:
            continue
        message = item.get("message")
        text = message.get("value") if isinstance(message, Mapping) else message
        severity = str(item.get("severity", "error")).lower()
        kind = {"error": "E", "warning": "W", "info": "I", "success": "S", "abort": "A"}.get(
            severity, "E"
        )
        found.append(SapMessage(kind, match[1], match[2], str(text or "")[:MAX_TEXT]))
    # A primeira é a de fora, repetida nos detalhes: sem duplicar.
    unique: dict[str, SapMessage] = {}
    for message in found:
        unique.setdefault(f"{message.code}:{message.text}", message)
    return list(unique.values())


def from_soap_fault(text: str) -> list[SapMessage]:
    """SOAP Fault do PI/PO. Só os elementos `code` e `text` (do SystemError do adapter) ou
    `faultcode`/`faultstring`: o código do PI não é uma mensagem SAP de classe e número, então
    entra como tipo E com a classe `PI`."""
    # Texto de cliente: sem DTD nem entidades (nada de expansão) e com tamanho limitado.
    if len(text) > MAX_XML or UNSAFE_XML.search(text):
        return []
    try:
        root = ET.fromstring(text)  # noqa: S314 - DOCTYPE/ENTITY recusados acima
    except ET.ParseError:
        return []
    values = {
        element.tag.rsplit("}", 1)[-1].lower(): (element.text or "").strip()
        for element in root.iter()
    }
    if "fault" not in {element.tag.rsplit("}", 1)[-1].lower() for element in root.iter()}:
        return []
    code = values.get("code") or values.get("faultcode") or ""
    message = values.get("text") or values.get("faultstring") or ""
    if not code and not message:
        return []
    return [SapMessage("E", "PI", "000", f"{code}: {message}".strip(": ")[:MAX_TEXT])]


def parse(text: str) -> list[SapMessage]:
    stripped = text.strip()
    if stripped.startswith("<"):
        return from_soap_fault(stripped)
    if not stripped.startswith(("{", "[")):
        return []
    try:
        value = json.loads(stripped)
    except ValueError:
        return []
    if isinstance(value, Mapping):
        row = lower_keys(value)
        if isinstance(row.get("error"), Mapping):
            return from_odata(row["error"])
        for key in ("return", "bapiret2", "bapi_return"):
            if key in row:
                return from_bapiret2(row[key])
    return from_bapiret2(value)


def main(messages: list[SapMessage]) -> SapMessage | None:
    """A mais grave (A antes de E, antes de W…); no empate, a primeira."""
    return max(messages, key=lambda m: SEVERITY.get(m.type, 0), default=None)


def enrich(event: dict[str, Any]) -> dict[str, Any]:
    """Acrescenta o código e os atributos SAP ao Evento, sem tirar nada dele."""
    error = event.get("error") if isinstance(event.get("error"), dict) else None
    attributes = dict(event.get("attributes") or {})
    candidates = []
    if error and isinstance(error.get("message"), str):
        candidates.append(error["message"])
    candidates += [value for value in attributes.values() if isinstance(value, str)]
    messages: list[SapMessage] = []
    for text in candidates:
        messages = parse(text)
        if messages:
            break
    chosen = main(messages)
    if chosen is None:
        return event
    if chosen.id.upper() == "PI":
        # SOAP Fault do PI/PO: falha técnica do middleware, não mensagem SAP de classe e número.
        # Fica como atributo próprio e nunca como recusa de negócio.
        if len(attributes) < MAX_ATTRIBUTES or "sap_pi_fault" in attributes:
            attributes["sap_pi_fault"] = chosen.text
        enriched = {**event, "attributes": attributes}
        if error is None:
            enriched["error"] = {"category": "UNKNOWN", "message": chosen.text}
            if event.get("severity") not in ("ERROR", "CRITICAL"):
                enriched["severity"] = "ERROR"
        return enriched
    extra = {
        "sap_message_type": chosen.type,
        "sap_message_id": chosen.id.upper(),
        "sap_message_number": chosen.number.zfill(3),
        "sap_message": chosen.text,
    }
    # Até o limite de 64 atributos do contrato, na ordem de importância.
    for name, value in extra.items():
        if name in attributes or len(attributes) < MAX_ATTRIBUTES:
            attributes[name] = value
    enriched = {**event, "attributes": attributes}
    if chosen.type in ("E", "A"):
        found = dict(error or {"category": "BUSINESS_REJECTION"})
        found.setdefault("code", chosen.code)
        if found.get("category") in (None, "UNKNOWN"):
            found["category"] = "BUSINESS_REJECTION"
        found.setdefault("message", chosen.text)
        enriched["error"] = found
        if enriched.get("severity") not in ("ERROR", "CRITICAL"):
            enriched["severity"] = "ERROR"
    return enriched


# Presets de importação: cabeçalhos em inglês e português das exportações ALV.
def column(row: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return None


def moment(row: Mapping[str, Any]) -> str | None:
    date = column(row, "date", "data", "created on", "criado em", "data de criação")
    time = column(row, "time", "hora", "time created", "hora de criação")
    if date and time:
        return f"{date} {time}"
    return date


IDOC_ERRORS = {"51", "56", "63", "65", "66", "69"}
SLG1_SEVERITY = {"A": "CRITICAL", "E": "ERROR", "W": "WARNING", "I": "INFO", "S": "INFO"}


def adapt_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Reconhece pelo cabeçalho uma linha exportada da SM58, da SLG1 ou da lista de status de
    IDoc e a reescreve com as chaves que `to_event` lê. Outras linhas passam como vieram."""
    row = {str(key).strip().lower(): value for key, value in record.items()}
    keys = set(row)
    if {"function module", "transaction id"} <= keys or {
        "módulo de função",
        "id de transação",
    } <= keys:
        return {
            "timestamp": moment(row),
            "operation": column(row, "function module", "módulo de função"),
            "execution_id": column(row, "transaction id", "id de transação"),
            "severity": "ERROR",
            "message": column(row, "status text", "texto de status"),
            "sap_target_system": column(row, "target system", "sistema de destino"),
            "sap_export": "SM58",
        }
    if {"idoc number", "status"} <= keys or {"número do idoc", "status"} <= keys:
        status = (column(row, "status") or "").lstrip("0") or "0"
        failed = status in IDOC_ERRORS
        return {
            "timestamp": moment(row),
            "operation": column(row, "message type", "tipo de mensagem") or "IDoc",
            "execution_id": column(row, "idoc number", "número do idoc"),
            "severity": "ERROR" if failed else "INFO",
            "message": column(row, "status text", "texto de status"),
            **({"error_code": f"IDOC {status}"} if failed else {}),
            "idoc_status": status,
            "sap_partner": column(row, "partner number", "número do parceiro"),
            "sap_export": "IDOC",
        }
    if {"message type", "message number"} <= keys or {
        "tipo de mensagem",
        "número da mensagem",
    } <= keys:
        kind = (column(row, "message type", "tipo de mensagem") or "I").upper()[:1]
        klass = column(row, "message class", "msg. class", "classe de mensagem")
        number = column(row, "message number", "número da mensagem")
        obj, sub = column(row, "object", "objeto"), column(row, "subobject", "subobjeto")
        severity = SLG1_SEVERITY.get(kind, "INFO")
        return {
            "timestamp": moment(row),
            "operation": "/".join(part for part in (obj, sub) if part) or "SLG1",
            "execution_id": column(row, "external id", "id externo"),
            "severity": severity,
            "message": column(row, "message text", "texto da mensagem"),
            **(
                {"error_code": f"{klass.upper()} {number.zfill(3)}"}
                if klass and number and severity in ("ERROR", "CRITICAL")
                else {}
            ),
            "sap_message_type": kind,
            **({"sap_message_id": klass.upper()} if klass else {}),
            **({"sap_message_number": number.zfill(3)} if number else {}),
            "sap_export": "SLG1",
        }
    return record
