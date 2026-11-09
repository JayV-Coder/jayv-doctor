"""Entrada do Cloud Logging (`LogEntry`) → Evento no Contrato v1 (sem `integration_id`)."""

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from aid_connectors.base import stable_uuid7
from aid_connectors.common import STATUS_CATEGORIES

SEVERITIES = {
    "DEFAULT": "INFO",
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "NOTICE": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
    "ALERT": "CRITICAL",
    "EMERGENCY": "CRITICAL",
}
MESSAGE_CATEGORIES = [
    ("TIMEOUT", re.compile(r"(?i)time[d ]?\s?out|deadline exceeded")),
    ("RATE_LIMIT", re.compile(r"(?i)too many requests|rate limit|quota")),
    ("AUTH", re.compile(r"(?i)unauthori[sz]ed|forbidden|permission denied")),
    ("CONNECTIVITY", re.compile(r"(?i)connection (refused|reset)|unreachable")),
]
NANOS = re.compile(r"(\.\d{6})\d+")
ATTRIBUTE = re.compile(r"[^a-z0-9_]+")


def origin_id(entry: Mapping[str, Any]) -> str:
    """insertId, ou o hash da entrada quando ele falta: duas entradas diferentes no mesmo
    instante não podem virar o mesmo event_id."""
    if entry.get("insertId"):
        return str(entry["insertId"])
    canonical = json.dumps(entry, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def timestamp(value: str) -> datetime:
    """O Logging usa nanossegundos; o contrato aceita até microssegundos."""
    return datetime.fromisoformat(NANOS.sub(r"\1", value).replace("Z", "+00:00"))


def category(status: int | None, message: str | None) -> str:
    if status in STATUS_CATEGORIES:
        return STATUS_CATEGORIES[status]
    for name, pattern in MESSAGE_CATEGORIES:
        if message and pattern.search(message):
            return name
    return "UNKNOWN"


def attribute_name(key: str) -> str | None:
    name = ATTRIBUTE.sub("_", key.lower()).strip("_")[:40]
    return name if name and name[0].isalpha() else None


def attributes(*sources: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            name = attribute_name(str(key))
            if name is None or name in flat or len(flat) >= 64:
                continue
            if isinstance(value, bool | int | float) or value is None:
                flat[name] = value
            elif isinstance(value, str):
                flat[name] = value[:200]
    return flat


def to_event(entry: Mapping[str, Any]) -> dict[str, Any]:
    payload: Mapping[str, Any] = entry.get("jsonPayload") or {}
    labels: Mapping[str, Any] = entry.get("labels") or {}
    resource: Mapping[str, Any] = entry.get("resource") or {}
    resource_labels: Mapping[str, Any] = resource.get("labels") or {}
    http: Mapping[str, Any] = entry.get("httpRequest") or {}
    moment = timestamp(str(entry["timestamp"]))
    severity = SEVERITIES.get(str(entry.get("severity", "DEFAULT")), "INFO")
    raw_message = payload.get("message") or entry.get("textPayload")
    # `message` pode vir como objeto ou número no jsonPayload.
    message = (
        None
        if raw_message is None
        else raw_message
        if isinstance(raw_message, str)
        else json.dumps(raw_message, ensure_ascii=False)
    )
    status = http.get("status")
    status = int(status) if isinstance(status, int | str) and str(status).isdigit() else None

    event: dict[str, Any] = {
        "schema_version": "1.0",
        "event_id": stable_uuid7(f"gcp:{origin_id(entry)}:{entry['timestamp']}", moment),
        "timestamp": moment.isoformat(),
        "source": {
            "provider": "gcp",
            "service": str(
                resource_labels.get("service_name") or resource.get("type") or "logging"
            )[:128],
            "resource": str(resource.get("type") or "global")[:256],
        },
        "operation": str(
            payload.get("operation")
            or labels.get("operation")
            or http.get("requestMethod")
            or str(entry.get("logName", "")).rsplit("/", 1)[-1]
            or "desconhecida"
        )[:128],
        "severity": severity,
    }
    trace = entry.get("trace")
    if trace:
        event["trace_id"] = str(trace).rsplit("/", 1)[-1][:256]
    execution = labels.get("execution_id") or payload.get("execution_id")
    if execution:
        event["execution_id"] = str(execution)[:256]
    if severity in {"ERROR", "CRITICAL"} or (status is not None and status >= 400):
        error: dict[str, Any] = {"category": category(status, message)}
        if status is not None and 100 <= status <= 599:
            error["http_status"] = status
        if message:
            error["message"] = str(message)[:8192]
        event["error"] = error
    used = {"message", "operation", "execution_id"}
    extra = attributes({k: v for k, v in payload.items() if k not in used}, labels)
    extra.pop("execution_id", None)
    if extra:
        event["attributes"] = extra
    return event
