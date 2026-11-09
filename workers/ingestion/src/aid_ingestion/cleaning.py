"""Sanitização de um Evento já no Contrato v1, igual para Importação e para a API.

- Nunca sanitizados: versão, ids gerados ou validados pela plataforma, data e severidade.
- Identificadores (`execution_id`, `trace_id`, `source.service`, `source.resource`): sanitizados,
  menos o detector de cartão, porque um IDoc de 16 dígitos passa no Luhn e é um id.
- O resto (operação, erro, atributos, contexto): sanitização completa.

Depois, os textos voltam aos limites do contrato: um marcador pode deixar o valor mais longo.
"""

from collections import Counter
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from aid_security import Sanitizer, derive_tenant_key

from aid_ingestion.sap import enrich

UNTOUCHED = {"schema_version", "event_id", "integration_id", "timestamp", "severity"}
IDENTIFIERS = ("execution_id", "trace_id")
LIMITS = {
    "operation": 128,
    "execution_id": 256,
    "trace_id": 256,
}
SOURCE_LIMITS = {"service": 128, "resource": 256}
ERROR_LIMITS = {"code": 128, "message": 8192}
CONTEXT_LIMITS = {"entity_type": 64, "entity_reference": 256}
ATTRIBUTE_LIMIT = 200


def clip(values: dict[str, Any], limits: Mapping[str, int]) -> None:
    for key, limit in limits.items():
        if isinstance(values.get(key), str):
            values[key] = values[key][:limit]


def fit_contract(event: dict[str, Any]) -> dict[str, Any]:
    clip(event, LIMITS)
    for key, limits in (("source", SOURCE_LIMITS), ("error", ERROR_LIMITS)):
        if isinstance(event.get(key), dict):
            clip(event[key], limits)
    if isinstance(event.get("business_context"), dict):
        clip(event["business_context"], CONTEXT_LIMITS)
    if isinstance(event.get("attributes"), dict):
        clip(event["attributes"], dict.fromkeys(event["attributes"], ATTRIBUTE_LIMIT))
    return event


class EventSanitizer:
    def __init__(self, master_key: bytes, tenant_id: str) -> None:
        key = derive_tenant_key(master_key, UUID(tenant_id))
        self.content = Sanitizer(reference_key=key)
        self.identifiers = Sanitizer(reference_key=key, exclude_kinds=("cartao",))

    def __call__(self, event: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """O Evento sanitizado e o relatório (`counts`, `truncated`) que vai para o banco."""
        # Respostas SAP (BAPIRET2, OData, SOAP Fault) viram código e atributos antes da
        # Sanitização, igual para Importação, API e Conectores (#38).
        event = enrich(dict(event))
        content = {
            key: value
            for key, value in event.items()
            if key not in UNTOUCHED and key not in IDENTIFIERS and key != "source"
        }
        ids: dict[str, Any] = {key: event[key] for key in IDENTIFIERS if key in event}
        source = dict(event.get("source") or {})
        ids["source"] = {key: value for key, value in source.items() if key != "provider"}
        cleaned_content, content_report = self.content.sanitize(content)
        cleaned_ids, ids_report = self.identifiers.sanitize(ids)
        cleaned_source = {"provider": source.get("provider"), **cleaned_ids.pop("source")}
        merged = {**event, **cleaned_content, **cleaned_ids, "source": cleaned_source}
        counts = Counter(content_report.counts) + Counter(ids_report.counts)
        report = {
            "counts": dict(counts),
            "truncated": content_report.truncated + ids_report.truncated,
        }
        return fit_contract(merged), report


def secrets_removed(report: Mapping[str, Any]) -> int:
    return sum(count for kind, count in report["counts"].items() if kind != "referencia")
