"""Registro bruto (já sanitizado) → payload do Contrato de evento v1.

Os nomes de campo variam por sistema (SAP, Salesforce, GCP, exportações à mão): cada campo do
contrato tem uma lista de nomes aceitos, e o que sobra vira `attributes`. Linha sem data legível
é rejeitada com o motivo, que vai para `import_rejections`.
"""

import math
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

SCHEMA_VERSION = "1.0"
# Data sem fuso: os clientes são brasileiros, e o SAP costuma registrar no horário local.
LOCAL = ZoneInfo("America/Sao_Paulo")
OLDEST = datetime(2000, 1, 1, tzinfo=UTC)
FUTURE_TOLERANCE = timedelta(days=1)

TIMESTAMP_KEYS = ("timestamp", "time", "@timestamp", "datetime", "date", "ts", "data_hora", "data")
SEVERITY_KEYS = ("severity", "severidade", "level", "nivel", "log_level", "msgty", "type")
OPERATION_KEYS = (
    "operation",
    "operacao",
    "bapi",
    "method",
    "action",
    "event",
    "evento",
    "endpoint",
)
EXECUTION_KEYS = (
    "execution_id",
    "correlation_id",
    "message_id",
    "transaction_id",
    "docnum",
    "idoc",
)
TRACE_KEYS = ("trace_id", "traceid", "trace")
MESSAGE_KEYS = ("message", "mensagem", "msg", "error_message", "text", "texto")
STATUS_KEYS = ("http_status", "status_code", "status", "http_code")
CODE_KEYS = ("error_code", "code", "codigo", "msgno")

SEVERITIES = {
    "debug": "DEBUG",
    "trace": "DEBUG",
    "d": "DEBUG",
    "info": "INFO",
    "information": "INFO",
    "notice": "INFO",
    "i": "INFO",
    "s": "INFO",
    "warn": "WARNING",
    "warning": "WARNING",
    "aviso": "WARNING",
    "w": "WARNING",
    "error": "ERROR",
    "erro": "ERROR",
    "err": "ERROR",
    "e": "ERROR",
    "critical": "CRITICAL",
    "crit": "CRITICAL",
    "fatal": "CRITICAL",
    "emergency": "CRITICAL",
    "alert": "CRITICAL",
    "a": "CRITICAL",
    "x": "CRITICAL",
}

# Ordem importa: o primeiro padrão que casar define a categoria.
CATEGORIES = [
    ("TIMEOUT", re.compile(r"(?i)time[d ]?\s?out|tempo esgotado|deadline exceeded"), {408, 504}),
    ("AUTH", re.compile(r"(?i)unauthori[sz]ed|forbidden|auth|token|credencia|senha"), {401, 403}),
    ("RATE_LIMIT", re.compile(r"(?i)rate limit|too many requests|quota|limite de"), {429}),
    ("DUPLICATE", re.compile(r"(?i)duplicat|já existe|already exists"), {409}),
    ("VALIDATION", re.compile(r"(?i)invalid|inválid|obrigatóri|required|validation"), {400, 422}),
    (
        "CONNECTIVITY",
        re.compile(r"(?i)connection (refused|reset)|unreachable|dns|recusou a conexão"),
        {502, 503},
    ),
]

ATTRIBUTE_NAME = re.compile(r"[^a-z0-9_]+")
MAX_ATTRIBUTES = 64
MAX_ATTRIBUTE_TEXT = 200


class RejectedLineError(ValueError):
    """Linha que não vira Evento; a mensagem é o motivo mostrado ao Usuário."""


def uuid7(now: datetime) -> str:
    """UUIDv7 (RFC 9562): 48 bits de milissegundos e o resto aleatório."""
    millis = int(now.timestamp() * 1000)
    value = (millis << 80) | (uuid.uuid4().int & ((1 << 80) - 1))
    value = (value & ~(0xF << 76)) | (0x7 << 76)
    value = (value & ~(0x3 << 62)) | (0x2 << 62)
    return str(uuid.UUID(int=value))


def pick(record: Mapping[str, Any], keys: tuple[str, ...]) -> tuple[str, Any] | None:
    lowered = {str(key).lower(): key for key in record}
    for key in keys:
        if key in lowered and record[lowered[key]] not in (None, ""):
            return lowered[key], record[lowered[key]]
    return None


def parse_timestamp(value: Any, now: datetime) -> datetime:
    if isinstance(value, int | float) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise RejectedLineError("data ilegível")
        seconds = value / 1000 if value > 1e11 else value
        try:
            moment = datetime.fromtimestamp(seconds, UTC)
        except (ValueError, OverflowError, OSError) as exc:
            raise RejectedLineError("data fora do intervalo aceito") from exc
    elif isinstance(value, str) and value.strip().isdigit() and len(value.strip()) in (10, 13):
        # Epoch em texto (CSV não tem tipo): 10 dígitos são segundos, 13 são milissegundos.
        return parse_timestamp(int(value.strip()), now)
    elif isinstance(value, str):
        moment = parse_text_timestamp(value.strip())
    else:
        raise RejectedLineError("data ilegível")
    if not OLDEST <= moment <= now + FUTURE_TOLERANCE:
        raise RejectedLineError("data fora do intervalo aceito")
    return moment


def parse_text_timestamp(text: str) -> datetime:
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        moment = None
    if moment is None:
        for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%Y%m%d%H%M%S"):
            try:
                moment = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
    if moment is None:
        raise RejectedLineError("data ilegível")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=LOCAL)
    return moment.astimezone(UTC)


def severity_of(record: Mapping[str, Any]) -> str:
    found = pick(record, SEVERITY_KEYS)
    if found is None:
        return "INFO"
    return SEVERITIES.get(str(found[1]).strip().lower(), "INFO")


def status_of(record: Mapping[str, Any]) -> int | None:
    found = pick(record, STATUS_KEYS)
    if found is None:
        return None
    try:
        status = int(str(found[1]).strip())
    except ValueError:
        return None
    return status if 100 <= status <= 599 else None


def error_of(
    record: Mapping[str, Any], severity: str, message: str | None, status: int | None
) -> dict[str, Any] | None:
    if severity not in {"ERROR", "CRITICAL"} and not (status and status >= 400):
        return None
    category = "UNKNOWN"
    for name, pattern, statuses in CATEGORIES:
        if (message and pattern.search(message)) or (status in statuses):
            category = name
            break
    error: dict[str, Any] = {"category": category}
    if status is not None:
        error["http_status"] = status
    code = pick(record, CODE_KEYS)
    if code is not None and code[0] not in STATUS_KEYS:
        error["code"] = str(code[1])[:128]
    if message:
        error["message"] = message[:8192]
    return error


def attribute_name(key: str) -> str | None:
    name = ATTRIBUTE_NAME.sub("_", key.strip().lower()).strip("_")[:40]
    if not name or not name[0].isalpha():
        return None
    return name


def attributes_of(record: Mapping[str, Any], used: set[str]) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for key, value in record.items():
        if key in used or len(attributes) >= MAX_ATTRIBUTES:
            continue
        name = attribute_name(str(key))
        if name is None or name in attributes:
            continue
        if isinstance(value, bool | int | float) or value is None:
            attributes[name] = value
        elif isinstance(value, str):
            attributes[name] = value[:MAX_ATTRIBUTE_TEXT]
    return attributes


def to_event(
    record: Mapping[str, Any],
    integration_id: str,
    source: Mapping[str, str],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    timestamp = pick(record, TIMESTAMP_KEYS)
    if timestamp is None:
        raise RejectedLineError("linha sem data (timestamp)")
    moment = parse_timestamp(timestamp[1], now)
    used = {timestamp[0]}

    taken: dict[tuple[str, ...], str] = {}

    def take(keys: tuple[str, ...], limit: int) -> str | None:
        found = pick(record, keys)
        if found is None:
            return None
        used.add(found[0])
        taken[keys] = found[0]
        return str(found[1])[:limit]

    severity = severity_of(record)
    if (found := pick(record, SEVERITY_KEYS)) is not None:
        used.add(found[0])
    status = status_of(record)
    if (found := pick(record, STATUS_KEYS)) is not None and status is not None:
        used.add(found[0])
    operation = take(OPERATION_KEYS, 128) or "desconhecida"
    execution_id = take(EXECUTION_KEYS, 256)
    trace_id = take(TRACE_KEYS, 256)
    message = take(MESSAGE_KEYS, 8192)
    error = error_of(record, severity, message, status)
    if error and "code" in error and (found := pick(record, CODE_KEYS)) is not None:
        used.add(found[0])

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_id": uuid7(now),
        "integration_id": integration_id,
        "timestamp": moment.isoformat(),
        "source": dict(source),
        "operation": operation,
        "severity": severity,
    }
    if execution_id:
        payload["execution_id"] = execution_id
    if trace_id:
        payload["trace_id"] = trace_id
    if error:
        payload["error"] = error
    elif message:
        # Sem erro, a mensagem fica nos atributos, pela chave que de fato foi lida.
        used.discard(taken[MESSAGE_KEYS])
    attributes = attributes_of(record, used)
    if attributes:
        payload["attributes"] = attributes
    return payload
