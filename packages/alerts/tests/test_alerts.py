"""Regras de alerta (#41): validação, avaliação, silêncio e mensagem."""

from datetime import UTC, datetime

import pytest
from aid_alerts import (
    AlertError,
    IncidentFacts,
    in_quiet_hours,
    incident_matches,
    message_for_incident,
    parse_conditions,
    parse_quiet_hours,
    push_endpoint_allowed,
    webhook_allowed,
)

PRD_CRITICAL = IncidentFacts(
    id="inc-1",
    number=123,
    title="Timeout na criação de pedidos",
    severity="critical",
    environment="prd",
    integration_id="00000000-0000-4000-8000-0000000001a1",
    integration_name="Pedidos Salesforce → SAP",
)


def test_incidente_critico_em_prd_casa_com_a_regra_do_plantao() -> None:
    rule = parse_conditions(
        {"type": "incident", "min_severity": "critical", "environments": ["prd"]}
    )
    assert incident_matches(rule, PRD_CRITICAL, "opened")
    assert not incident_matches(rule, PRD_CRITICAL._replace(severity="high"), "opened")
    assert not incident_matches(rule, PRD_CRITICAL._replace(environment="hml"), "opened")
    only_opened = parse_conditions(
        {"type": "incident", "min_severity": "high", "events": ["opened"]}
    )
    assert not incident_matches(only_opened, PRD_CRITICAL, "updated")
    other = parse_conditions(
        {
            "type": "incident",
            "min_severity": "low",
            "integrations": ["00000000-0000-4000-8000-0000000001b1"],
        }
    )
    assert not incident_matches(other, PRD_CRITICAL, "opened")


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "sms"},
        {"type": "incident", "min_severity": "urgent"},
        {"type": "incident", "environments": ["prod"]},
        {"type": "error_rate", "threshold_pct": 0, "minutes": 10},
        {"type": "error_rate", "threshold_pct": 5, "minutes": 2},
        {"type": "diagnosis_review", "minutes": 0},
        {"type": "incident", "integrations": ["não é uuid"]},
        "incident",
    ],
)
def test_condicao_invalida_e_recusada(raw: object) -> None:
    with pytest.raises(AlertError):
        parse_conditions(raw)


def test_silencio_que_atravessa_a_meia_noite_no_fuso_da_regra() -> None:
    quiet = parse_quiet_hours({"start": "22:00", "end": "07:00", "timezone": "America/Sao_Paulo"})
    assert quiet is not None
    # 02:00 em São Paulo = 05:00 UTC.
    assert in_quiet_hours(quiet, datetime(2026, 11, 10, 5, 0, tzinfo=UTC))
    # 12:00 em São Paulo = 15:00 UTC.
    assert not in_quiet_hours(quiet, datetime(2026, 11, 10, 15, 0, tzinfo=UTC))
    assert parse_quiet_hours(None) is None
    with pytest.raises(AlertError):
        parse_quiet_hours({"start": "25:00", "end": "07:00"})


def test_mensagem_so_com_titulo_severidade_integracao_e_link() -> None:
    message = message_for_incident(PRD_CRITICAL, "https://app.doctor.test", "opened")
    assert message.url == "https://app.doctor.test/incidentes/inc-1"
    assert message.title == "Incidente crítico #123"
    assert message.body == "Timeout na criação de pedidos · Pedidos Salesforce → SAP · prd"


@pytest.mark.parametrize(
    ("kind", "url", "ok"),
    [
        ("slack", "https://hooks.slack.com/services/T0/B0/xyz", True),
        ("slack", "http://hooks.slack.com/services/T0/B0/xyz", False),
        ("slack", "https://hooks.slack.com.evil.test/services/x", False),
        ("teams", "https://acme.webhook.office.com/webhookb2/abc", True),
        ("teams", "https://prod-12.westus.logic.azure.com:443/workflows/abc", True),
        ("teams", "https://user:x@acme.webhook.office.com/webhookb2/abc", False),
        ("teams", "https://10.0.0.5/webhook", False),
    ],
)
def test_webhook_so_nos_hosts_do_slack_e_do_teams(kind: str, url: str, ok: bool) -> None:
    assert webhook_allowed(kind, url) is ok


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("https://fcm.googleapis.com/fcm/send/abc", True),
        ("https://updates.push.services.mozilla.com/wpush/v2/abc", True),
        ("https://web.push.apple.com/QGx", True),
        ("https://wns2-bn3p.notify.windows.com/w/?token=x", True),
        ("https://metadata.google.internal/computeMetadata", False),
        ("https://10.0.0.5/push", False),
        ("http://fcm.googleapis.com/fcm/send/abc", False),
        ("https://fcm.googleapis.com.evil.test/x", False),
    ],
)
def test_push_so_nos_servicos_dos_navegadores(url: str, ok: bool) -> None:
    assert push_endpoint_allowed(url) is ok
