"""Condições das Regras de alerta, horário de silêncio e o texto das notificações.

A mensagem leva só título, severidade, Integração, Ambiente e o link para o Incidente: nada de
log, Evidência ou dado de negócio, porque sai para Slack, Teams, e-mail e a tela de bloqueio do
celular.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, NamedTuple
from urllib.parse import urlparse
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SEVERITIES = ("low", "medium", "high", "critical")
SEVERITY_PT = {"low": "baixa", "medium": "média", "high": "alta", "critical": "crítico"}
ENVIRONMENTS = ("dev", "hml", "prd")
EVENTS = ("opened", "updated")
TYPES = ("incident", "error_rate", "connector_failing", "diagnosis_review")
CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
# Hosts dos webhooks: Slack (Incoming Webhook do app) e Teams (Incoming Webhook ou Workflows).
WEBHOOK_HOSTS = {
    "slack": re.compile(r"^hooks\.slack\.com$"),
    "teams": re.compile(
        r"^([a-z0-9-]+\.)*(webhook\.office\.com|logic\.azure\.com|powerplatform\.com)$"
    ),
}


# Serviços de push dos navegadores: o `notifier` faz POST no endpoint da assinatura, então só
# estes hosts são aceitos (um endpoint qualquer seria SSRF a partir da plataforma).
PUSH_HOSTS = re.compile(
    r"^(fcm\.googleapis\.com|updates\.push\.services\.mozilla\.com"
    r"|([a-z0-9-]+\.)*push\.apple\.com|([a-z0-9-]+\.)*notify\.windows\.com)$"
)


class AlertError(ValueError):
    """Regra inválida; a mensagem diz o campo e a regra."""


@dataclass(frozen=True)
class Conditions:
    type: str
    min_severity: str = "high"
    environments: tuple[str, ...] = ()
    integrations: tuple[str, ...] = ()
    events: tuple[str, ...] = EVENTS
    threshold_pct: float = 5.0
    minutes: int = 10
    min_executions: int = 10

    def as_json(self) -> dict[str, Any]:
        base: dict[str, Any] = {"type": self.type}
        if self.type == "incident":
            base |= {
                "min_severity": self.min_severity,
                "environments": list(self.environments),
                "integrations": list(self.integrations),
                "events": list(self.events),
            }
        elif self.type == "error_rate":
            base |= {
                "threshold_pct": self.threshold_pct,
                "minutes": self.minutes,
                "min_executions": self.min_executions,
                "integrations": list(self.integrations),
            }
        elif self.type == "connector_failing":
            base |= {"integrations": list(self.integrations)}
        else:
            base |= {"minutes": self.minutes}
        return base


def _choices(raw: Any, name: str, allowed: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(item in allowed for item in raw):
        raise AlertError(f"{name}: lista com {', '.join(allowed)}")
    return tuple(dict.fromkeys(raw))


def _uuids(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or len(raw) > 50:
        raise AlertError("integrations: lista de ids de Integração")
    try:
        return tuple(dict.fromkeys(str(UUID(str(item))) for item in raw))
    except ValueError as exc:
        raise AlertError("integrations: lista de ids de Integração") from exc


def _number(raw: Any, name: str, low: float, high: float, default: float) -> float:
    value = default if raw is None else raw
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        raise AlertError(f"{name}: de {low:g} a {high:g}")
    return float(value)


def parse_conditions(raw: Any) -> Conditions:
    if not isinstance(raw, Mapping) or raw.get("type") not in TYPES:
        raise AlertError(f"type: um de {', '.join(TYPES)}")
    kind = str(raw["type"])
    if kind == "incident":
        severity = raw.get("min_severity", "high")
        if severity not in SEVERITIES:
            raise AlertError(f"min_severity: um de {', '.join(SEVERITIES)}")
        events = _choices(raw.get("events"), "events", EVENTS) or EVENTS
        return Conditions(
            kind,
            min_severity=str(severity),
            environments=_choices(raw.get("environments"), "environments", ENVIRONMENTS),
            integrations=_uuids(raw.get("integrations")),
            events=events,
        )
    if kind == "error_rate":
        return Conditions(
            kind,
            threshold_pct=_number(raw.get("threshold_pct"), "threshold_pct", 1, 100, 5),
            minutes=int(_number(raw.get("minutes"), "minutes", 5, 1440, 10)),
            min_executions=int(_number(raw.get("min_executions"), "min_executions", 1, 10_000, 10)),
            integrations=_uuids(raw.get("integrations")),
        )
    if kind == "connector_failing":
        return Conditions(kind, integrations=_uuids(raw.get("integrations")))
    return Conditions(kind, minutes=int(_number(raw.get("minutes"), "minutes", 5, 1440, 30)))


class IncidentFacts(NamedTuple):
    id: str
    number: int | None
    title: str
    severity: str
    environment: str
    integration_id: str
    integration_name: str


def incident_matches(rule: Conditions, incident: IncidentFacts, event: str) -> bool:
    if rule.type != "incident" or event not in rule.events:
        return False
    if incident.severity not in SEVERITIES:
        return False
    if SEVERITIES.index(incident.severity) < SEVERITIES.index(rule.min_severity):
        return False
    if rule.environments and incident.environment not in rule.environments:
        return False
    return not rule.integrations or incident.integration_id in rule.integrations


@dataclass(frozen=True)
class QuietHours:
    start: time
    end: time
    zone: ZoneInfo


def parse_quiet_hours(raw: Any) -> QuietHours | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise AlertError("quiet_hours: objeto com start, end e timezone")
    start, end = raw.get("start"), raw.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        raise AlertError("quiet_hours: start e end em HH:MM")
    if not CLOCK.match(start) or not CLOCK.match(end) or start == end:
        raise AlertError("quiet_hours: start e end em HH:MM, diferentes")
    try:
        zone = ZoneInfo(str(raw.get("timezone") or "America/Sao_Paulo"))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise AlertError("quiet_hours.timezone: fuso IANA, ex.: America/Sao_Paulo") from exc
    return QuietHours(time.fromisoformat(start), time.fromisoformat(end), zone)


def dump_quiet_hours(quiet: QuietHours | None) -> dict[str, str] | None:
    if quiet is None:
        return None
    return {
        "start": quiet.start.strftime("%H:%M"),
        "end": quiet.end.strftime("%H:%M"),
        "timezone": str(quiet.zone),
    }


def in_quiet_hours(quiet: QuietHours | None, now: datetime) -> bool:
    if quiet is None:
        return False
    local = now.astimezone(quiet.zone).time()
    if quiet.start < quiet.end:
        return quiet.start <= local < quiet.end
    # Atravessa a meia-noite (22:00 às 07:00).
    return local >= quiet.start or local < quiet.end


@dataclass(frozen=True)
class Message:
    title: str
    body: str
    url: str


def message_for_incident(incident: IncidentFacts, app_url: str, event: str) -> Message:
    number = f" #{incident.number}" if incident.number else ""
    prefix = "Incidente" if event == "opened" else "Incidente atualizado"
    return Message(
        title=f"{prefix} {SEVERITY_PT.get(incident.severity, incident.severity)}{number}",
        body=f"{incident.title} · {incident.integration_name} · {incident.environment}"[:300],
        url=f"{app_url.rstrip('/')}/incidentes/{incident.id}",
    )


def webhook_allowed(kind: str, url: str) -> bool:
    pattern = WEBHOOK_HOSTS.get(kind)
    if pattern is None:
        return False
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and port in (None, 443)
        and pattern.match(parsed.hostname or "") is not None
        and len(url) <= 1000
    )


def push_endpoint_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and port in (None, 443)
        and PUSH_HOSTS.match(parsed.hostname or "") is not None
        and len(url) <= 1000
    )
