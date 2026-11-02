"""OpenTelemetry com `tenant.id` nos spans; e-mail e nome nunca entram."""

import os

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

EXCLUDED_URLS = "healthz,readyz"


def annotate_span(tenant_id: str | None) -> None:
    if tenant_id:
        trace.get_current_span().set_attribute("tenant.id", tenant_id)


# Só com OTEL_ENABLED=true: os exportadores exigem credenciais do GCP.
def configure(app: FastAPI) -> None:
    if os.environ.get("OTEL_ENABLED") != "true":
        return
    from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

    tracer_provider = TracerProvider()
    exporter = CloudTraceSpanExporter()  # type: ignore[no-untyped-call]
    tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(
        MeterProvider(
            metric_readers=[PeriodicExportingMetricReader(CloudMonitoringMetricsExporter())]
        )
    )
    FastAPIInstrumentor.instrument_app(app, excluded_urls=EXCLUDED_URLS)
