"""OpenTelemetry com `tenant.id` nos spans; e-mail e nome nunca entram. O trace da requisição
segue pela outbox até os workers (`aid_observability.tracing`, #34)."""

from aid_observability import logs, tracing
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

EXCLUDED_URLS = "healthz,readyz"


def annotate_span(tenant_id: str | None) -> None:
    if tenant_id:
        trace.get_current_span().set_attribute("tenant.id", tenant_id)
        logs.add(tenant_id=tenant_id)


def configure(app: FastAPI) -> None:
    """Logs JSON sempre; traces no Cloud Trace só com OTEL_ENABLED=true (exige credenciais)."""
    logs.configure_logging()
    if tracing.configure("api"):
        FastAPIInstrumentor.instrument_app(app, excluded_urls=EXCLUDED_URLS)
