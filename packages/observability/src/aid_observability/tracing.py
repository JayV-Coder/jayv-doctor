"""Contexto de trace W3C de ponta a ponta: API → outbox → Pub/Sub → workers.

A API e os workers põem o `traceparent` do span atual na sessão do banco (`doctor.traceparent`),
um trigger o grava em cada mensagem da outbox, o relay o publica como atributo do Pub/Sub e o
runtime dos workers abre o span da mensagem como filho dele. Um Evento injetado na API chega à
gravação em `doctor.events` no mesmo trace."""

import os
from collections.abc import Mapping

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

PROPAGATOR = TraceContextTextMapPropagator()
tracer = trace.get_tracer("aid")


def traceparent() -> str | None:
    """O `traceparent` do span atual, ou `None` fora de um trace (OTel desligado)."""
    carrier: dict[str, str] = {}
    PROPAGATOR.inject(carrier)
    return carrier.get("traceparent")


def context_from(attributes: Mapping[str, str]) -> Context:
    """Contexto pai a partir dos atributos da mensagem do Pub/Sub."""
    return PROPAGATOR.extract({k: v for k, v in attributes.items() if k == "traceparent"})


def configure(service: str) -> bool:
    """Liga o envio ao Cloud Trace com OTEL_ENABLED=true (o exportador exige credenciais)."""
    if os.environ.get("OTEL_ENABLED") != "true":
        return False
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))  # type: ignore[no-untyped-call]
    trace.set_tracer_provider(provider)
    return True
