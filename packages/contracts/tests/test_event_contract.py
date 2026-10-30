"""Contrato de evento v1: as fixtures definem o comportamento esperado em Python e em TS."""

import json
from pathlib import Path
from typing import Any

import pytest
from aid_contracts import (
    EVENT_SCHEMA_V1,
    EventV1,
    EventValidationError,
    to_json_dict,
    validate_event,
)
from hypothesis import HealthCheck, given, settings
from hypothesis_jsonschema import from_schema

CONTRACTS = Path(__file__).resolve().parent.parent
FIXTURES = CONTRACTS / "fixtures" / "event.v1"


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize("path", sorted((FIXTURES / "valid").glob("*.json")), ids=lambda p: p.stem)
def test_valid_fixture_is_accepted(path: Path) -> None:
    event = validate_event(_load(path))

    assert isinstance(event, EventV1)


@pytest.mark.parametrize(
    "path", sorted((FIXTURES / "invalid").glob("*.json")), ids=lambda p: p.stem
)
def test_invalid_fixture_is_rejected(path: Path) -> None:
    with pytest.raises(EventValidationError):
        validate_event(_load(path))


def test_tenant_id_is_rejected_with_explicit_reason() -> None:
    with pytest.raises(EventValidationError) as excinfo:
        validate_event(_load(FIXTURES / "invalid" / "with-tenant-id.json"))

    assert any("tenant_id" in error for error in excinfo.value.errors)


def test_packaged_schema_matches_canonical_schema() -> None:
    canonical = _load(CONTRACTS / "schemas" / "event.v1.json")

    assert canonical == EVENT_SCHEMA_V1


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(from_schema(EVENT_SCHEMA_V1))
def test_every_schema_valid_event_round_trips(payload: dict[str, Any]) -> None:
    event = validate_event(payload)

    again = validate_event(to_json_dict(event))

    assert again == event
