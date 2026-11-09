"""Traces, logs e métricas da plataforma (ticket #34)."""

import json
import logging

import httpx
import pytest
from aid_observability.logs import JsonFormatter, bind
from aid_observability.metrics import MonitoringWriter
from aid_observability.tracing import context_from, traceparent
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

PROVIDER = TracerProvider()
TRACER = PROVIDER.get_tracer("teste")


def record(message: str, *args: object, exc: bool = False) -> logging.LogRecord:
    info = None
    if exc:
        try:
            email = "ana" + "@acme.com.br"
            raise ValueError(
                f"insert falhou\nDETAIL:  Key (tenant_id, email)=(t, {email}) already exists."
                f"\n[parameters: ('{email}', 'segredo')]"
            )
        except ValueError:
            import sys

            info = sys.exc_info()
    return logging.LogRecord("aid.teste", logging.ERROR, __file__, 1, message, args, info)


def test_traceparent_vai_e_volta_pelo_atributo_da_mensagem() -> None:
    assert traceparent() is None
    with TRACER.start_as_current_span("api") as span:
        header = traceparent()
        trace_id = span.get_span_context().trace_id
    assert header is not None
    assert header.startswith(f"00-{trace_id:032x}-")
    parent = context_from({"traceparent": header, "tenant_id": "t"})
    with TRACER.start_as_current_span("worker", context=parent) as child:
        assert child.get_span_context().trace_id == trace_id


def test_log_json_com_trace_e_so_os_campos_permitidos() -> None:
    formatter = JsonFormatter(project="aid-test")
    with (
        TRACER.start_as_current_span("x") as span,
        bind(tenant_id="t1", request_id="r1", email="ana@acme.com.br"),
    ):
        entry = json.loads(formatter.format(record("lote %s gravado", "b1")))
    assert entry["message"] == "lote b1 gravado"
    assert entry["severity"] == "ERROR"
    assert (entry["tenant_id"], entry["request_id"]) == ("t1", "r1")
    assert "email" not in entry
    trace_id = f"{span.get_span_context().trace_id:032x}"
    assert entry["logging.googleapis.com/trace"] == f"projects/aid-test/traces/{trace_id}"


def test_traceback_perde_os_parametros_do_sql() -> None:
    entry = json.loads(JsonFormatter(project="p").format(record("falhou", exc=True)))
    assert "ana@acme.com.br" not in entry["exception"]
    assert "detalhe omitido" in entry["exception"]


def test_configurar_os_logs_nao_tira_os_outros_handlers() -> None:
    from aid_observability.logs import configure_logging

    other = logging.NullHandler()
    root = logging.getLogger()
    root.addHandler(other)
    try:
        configure_logging()
        configure_logging()
        assert other in root.handlers
        assert sum(isinstance(h.formatter, JsonFormatter) for h in root.handlers) == 1
    finally:
        root.removeHandler(other)
        root.handlers = [h for h in root.handlers if not isinstance(h.formatter, JsonFormatter)]


@pytest.mark.asyncio
async def test_metricas_vao_para_o_cloud_monitoring_com_o_token_da_conta() -> None:
    sent: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.host == "metadata.google.internal":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        written = await MonitoringWriter("aid-test", client).gauges(
            {"outbox_lag_seconds": 12, "connectors_failing": 0}
        )
    assert written == 2
    body = json.loads(sent[-1].content)
    types = [series["metric"]["type"] for series in body["timeSeries"]]
    assert types == [
        "custom.googleapis.com/aid/connectors_failing",
        "custom.googleapis.com/aid/outbox_lag_seconds",
    ]
    assert sent[-1].url.path == "/v3/projects/aid-test/timeSeries"


def test_fora_de_um_trace_o_span_atual_e_invalido() -> None:
    assert not trace.get_current_span().get_span_context().is_valid
