"""Regras de alerta e notificações (ticket #41): o que a API valida e o `notifier` avalia."""

from aid_alerts.rules import (
    SEVERITIES,
    AlertError,
    Conditions,
    IncidentFacts,
    Message,
    QuietHours,
    dump_quiet_hours,
    in_quiet_hours,
    incident_matches,
    message_for_incident,
    parse_conditions,
    parse_quiet_hours,
    push_endpoint_allowed,
    webhook_allowed,
)

__all__ = [
    "SEVERITIES",
    "AlertError",
    "Conditions",
    "IncidentFacts",
    "Message",
    "QuietHours",
    "dump_quiet_hours",
    "in_quiet_hours",
    "incident_matches",
    "message_for_incident",
    "parse_conditions",
    "parse_quiet_hours",
    "push_endpoint_allowed",
    "webhook_allowed",
]
