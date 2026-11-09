"""Registro do Salesforce → Evento no Contrato v1 (sem `integration_id`)."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from aid_connectors.base import stable_uuid7
from aid_connectors.common import STATUS_CATEGORIES
from aid_connectors.salesforce.soql import Source

SEVERITIES = {
    "debug": "DEBUG",
    "info": "INFO",
    "information": "INFO",
    "warning": "WARNING",
    "warn": "WARNING",
    "error": "ERROR",
    "fatal": "CRITICAL",
    "critical": "CRITICAL",
}


def moment(value: Any) -> datetime:
    """`2026-11-10T14:05:00.000+0000` (formato do Salesforce) ou ISO; data pura vira meia-noite."""
    text = str(value)
    if len(text) == 10:
        text += "T00:00:00+00:00"
    if text.endswith("+0000"):
        text = text[:-5] + "+00:00"
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def status_code(value: Any) -> int | None:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return None
    return code if 100 <= code <= 599 else None


def to_event(
    record: Mapping[str, Any], source: Source, config: Mapping[str, Any]
) -> dict[str, Any]:
    at = moment(record.get(source.timestamp_field) or record["SystemModstamp"])
    if source.object == "ApexLog":
        ok = str(record.get("Status", "")).lower() == "success"
        operation = str(record.get("Operation") or "ApexLog")
        severity = "INFO" if ok else "ERROR"
        message = None if ok else str(record.get("Status"))[:8192]
        code = None
        execution = None
    elif source.object == "EventLogFile":
        operation = f"EventLogFile:{record.get('EventType', 'desconhecido')}"
        severity, message, code, execution = "INFO", None, None, None
    else:
        fields = config.get("integration_log", {})
        operation = str(record.get(fields.get("operation_field") or "", "") or source.object)
        raw = str(record.get(fields.get("severity_field") or "", "") or "").lower()
        code = status_code(record.get(fields.get("status_code_field") or ""))
        severity = SEVERITIES.get(raw, "ERROR" if code and code >= 400 else "INFO")
        message = record.get(fields.get("message_field") or "")
        message = None if message in (None, "") else str(message)[:8192]
        execution = record.get(fields.get("execution_field") or "")
    event: dict[str, Any] = {
        "schema_version": "1.0",
        "event_id": stable_uuid7(f"salesforce:{source.object}:{record['Id']}", at),
        "timestamp": at.isoformat(),
        "source": {"provider": "salesforce", "service": source.object},
        "operation": operation[:128],
        "severity": severity,
        "attributes": {"salesforce_id": str(record["Id"])},
    }
    if execution:
        event["execution_id"] = str(execution)[:256]
    if severity in ("ERROR", "CRITICAL") or code:
        event["error"] = {
            "category": STATUS_CATEGORIES.get(code or 0, "UNKNOWN"),
            **({"http_status": code} if code else {}),
            **({"message": message} if message else {}),
        }
    return event
