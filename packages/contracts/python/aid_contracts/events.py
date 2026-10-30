"""Validação do Contrato de evento v1.

O JSON Schema em `schemas/event.v1.json` é a fonte da verdade: a validação TS (Ajv) usa o
mesmo arquivo, então os dois lados aceitam e rejeitam exatamente os mesmos payloads.
O modelo Pydantic gerado (`EventV1`) é a forma tipada do Evento já validado.
"""

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any, Final

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from aid_contracts.event_v1 import EventV1

EVENT_SCHEMA_V1: Final[dict[str, Any]] = json.loads(
    files("aid_contracts").joinpath("schemas/event.v1.json").read_text(encoding="utf-8")
)
TENANT_ID_REJECTED: Final = (
    "tenant_id não é aceito no payload: o tenant vem da identidade autenticada do Conector"
)

_VALIDATOR: Final = Draft202012Validator(EVENT_SCHEMA_V1, format_checker=FormatChecker())


class EventValidationError(ValueError):
    """O payload não obedece ao Contrato de evento v1."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def validate_event(payload: Mapping[str, Any]) -> EventV1:
    """Valida um payload contra o Contrato de evento v1 e devolve o Evento tipado."""
    errors = [TENANT_ID_REJECTED] if "tenant_id" in payload else []
    errors += [
        f"{error.json_path}: {error.message}"
        for error in sorted(_VALIDATOR.iter_errors(payload), key=lambda e: e.json_path)
    ]
    if errors:
        raise EventValidationError(errors)
    try:
        event: EventV1 = EventV1.model_validate(payload)
    except ValidationError as exc:  # o schema aceitou, mas o modelo não: divergência a corrigir
        raise EventValidationError([str(err["msg"]) for err in exc.errors()]) from exc
    return event


def to_json_dict(event: EventV1) -> dict[str, Any]:
    """Serializa o Evento de volta ao formato do contrato (só os campos informados)."""
    data: dict[str, Any] = event.model_dump(mode="json", exclude_unset=True)
    return data
