"""Contratos compartilhados do Integration AI Doctor."""

from aid_contracts.event_v1 import EventV1
from aid_contracts.events import (
    EVENT_SCHEMA_V1,
    TENANT_ID_REJECTED,
    EventValidationError,
    to_json_dict,
    validate_event,
)

__all__ = [
    "EVENT_SCHEMA_V1",
    "TENANT_ID_REJECTED",
    "EventV1",
    "EventValidationError",
    "to_json_dict",
    "validate_event",
]
