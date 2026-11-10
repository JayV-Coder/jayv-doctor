"""Mapa de identificadores (ticket #40): onde cada sistema guarda a mesma chave de negócio e
como normalizá-la, para o pedido `801XX0001` do Salesforce, o `SF-801XX0001` do middleware e o
`0000801XX0001` do SAP virarem a mesma chave.

Cada item de `keys` diz o sistema (o `source.provider` do Evento), o campo e as transformações,
em ordem. A chave do Evento é `<id do mapa>:<valor normalizado>`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

SYSTEMS = ("gcp", "salesforce", "sap", "aws", "azure", "mulesoft", "manual", "custom")
FIXED_FIELDS = ("execution_id", "trace_id", "operation", "source.resource", "error.code")
OPERATIONS = ("trim", "upper", "lower", "strip_leading_zeros", "strip_prefix", "strip_suffix")
WITH_VALUE = ("strip_prefix", "strip_suffix")
MAX_VALUE = 256
MAX_TRANSFORMS = 6


class MappingError(ValueError):
    """Mapa inválido; a mensagem diz o item e a regra, nunca um valor de Evento."""


@dataclass(frozen=True)
class KeySpec:
    system: str
    field: str
    transforms: tuple[tuple[str, str | None], ...] = ()


@dataclass(frozen=True)
class IdentifierMap:
    id: str
    keys: tuple[KeySpec, ...]
    window: timedelta


def _field_ok(field: str) -> bool:
    if field in FIXED_FIELDS:
        return True
    # `attributes.<nome>`, até dois níveis abaixo de attributes.
    parts = field.split(".")
    return (
        parts[0] == "attributes"
        and 2 <= len(parts) <= 3
        and all(0 < len(part) <= 64 and part.replace("_", "").isalnum() for part in parts[1:])
    )


def parse_keys(raw: Any) -> tuple[KeySpec, ...]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 6:
        raise MappingError("keys: lista com 1 a 6 itens")
    found = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise MappingError(f"keys[{index}]: objeto")
        system, field = item.get("system"), item.get("field")
        if system not in SYSTEMS:
            raise MappingError(f"keys[{index}].system: um de {', '.join(SYSTEMS)}")
        if not isinstance(field, str) or not _field_ok(field):
            raise MappingError(
                f"keys[{index}].field: {', '.join(FIXED_FIELDS)} ou attributes.<nome>"
            )
        transforms = item.get("transforms", [])
        if not isinstance(transforms, list) or len(transforms) > MAX_TRANSFORMS:
            raise MappingError(f"keys[{index}].transforms: lista com até {MAX_TRANSFORMS}")
        steps: list[tuple[str, str | None]] = []
        for position, step in enumerate(transforms):
            where = f"keys[{index}].transforms[{position}]"
            if not isinstance(step, Mapping) or step.get("op") not in OPERATIONS:
                raise MappingError(f"{where}.op: um de {', '.join(OPERATIONS)}")
            value = step.get("value")
            if step["op"] in WITH_VALUE:
                if not isinstance(value, str) or not 1 <= len(value) <= 32:
                    raise MappingError(f"{where}.value: texto de 1 a 32 caracteres")
                steps.append((step["op"], value))
            else:
                steps.append((step["op"], None))
        found.append(KeySpec(str(system), field, tuple(steps)))
    return tuple(found)


def dump_keys(keys: Sequence[KeySpec]) -> list[dict[str, Any]]:
    return [
        {
            "system": key.system,
            "field": key.field,
            "transforms": [
                {"op": op, "value": value} if value is not None else {"op": op}
                for op, value in key.transforms
            ],
        }
        for key in keys
    ]


def normalize(value: str, transforms: Sequence[tuple[str, str | None]]) -> str:
    for op, argument in transforms:
        if op == "trim":
            value = value.strip()
        elif op == "upper":
            value = value.upper()
        elif op == "lower":
            value = value.lower()
        elif op == "strip_leading_zeros":
            value = value.lstrip("0")
        elif op == "strip_prefix" and argument and value.startswith(argument):
            value = value[len(argument) :]
        elif op == "strip_suffix" and argument and value.endswith(argument):
            value = value[: -len(argument)]
    return value


def read_field(event: Mapping[str, Any], field: str) -> str | None:
    current: Any = event
    for part in field.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    if isinstance(current, bool) or current is None:
        return None
    if isinstance(current, int | str):
        return str(current)
    return None


def cross_keys(event: Mapping[str, Any], maps: Sequence[IdentifierMap]) -> tuple[str, ...]:
    """As chaves do Evento (no formato do Contrato: `source.provider`, `attributes` etc.)."""
    system = (event.get("source") or {}).get("provider")
    found: set[str] = set()
    for identifier_map in maps:
        for key in identifier_map.keys:
            if key.system != system:
                continue
            raw = read_field(event, key.field)
            if raw is None:
                continue
            value = normalize(raw, key.transforms)
            if value and len(value) <= MAX_VALUE:
                found.add(f"{identifier_map.id}:{value}")
    return tuple(sorted(found))
