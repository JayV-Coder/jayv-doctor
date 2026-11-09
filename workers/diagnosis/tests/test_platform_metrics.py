"""Métricas da plataforma (ticket #34): CPU e disco do Supabase e as medidas do banco."""

import json
import os
from typing import Any

import httpx
import pytest
from aid_diagnosis_worker.platform_metrics import cpu_and_disk, parse, push_metrics
from aid_observability.health import evaluate
from aid_observability.metrics import MonitoringWriter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")


def scrape(idle: float, user: float) -> str:
    return "\n".join(
        [
            "# HELP node_cpu_seconds_total Seconds the CPUs spent in each mode.",
            f'node_cpu_seconds_total{{cpu="0",mode="idle"}} {idle}',
            f'node_cpu_seconds_total{{cpu="0",mode="user"}} {user}',
            'node_filesystem_size_bytes{device="/dev/nvme1n1",mountpoint="/data"} 1000',
            'node_filesystem_avail_bytes{device="/dev/nvme1n1",mountpoint="/data"} 250',
            "pg_up NaN",
        ]
    )


def test_cpu_sai_da_diferenca_entre_duas_leituras_e_o_disco_da_pasta_do_banco() -> None:
    first, counters = cpu_and_disk(parse(scrape(100, 100)), {})
    assert "supabase_cpu_utilization" not in first
    assert first["supabase_disk_utilization"] == 0.75
    second, _ = cpu_and_disk(parse(scrape(110, 190)), counters)
    # 90 s ocupados de 100: 90%.
    assert second["supabase_cpu_utilization"] == 0.9


def test_saude_degradada_acima_dos_limites_dos_alertas() -> None:
    ok = evaluate({"outbox_lag_seconds": 30, "llm_error_rate_1h": 0.02, "outbox_stuck": 0})
    assert ok["status"] == "ok"
    bad = evaluate({"outbox_lag_seconds": 900, "llm_error_rate_1h": 0.2})
    assert bad["status"] == "degraded"
    assert bad["checks"]["outbox_lag_seconds"]["runbook"].endswith("outbox-lag.md")


@pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
@pytest.mark.asyncio
async def test_medidas_do_banco_e_do_supabase_vao_para_o_cloud_monitoring(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from doctor.platform_jobs where name = 'supabase_metrics'")
        )
    sent: list[dict[str, Any]] = []
    reads = iter([scrape(100, 100), scrape(150, 200)])

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "metadata.google.internal":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if request.url.path == "/customer/v1/privileged/metrics":
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(200, text=next(reads))
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        writer = MonitoringWriter("aid-test", client)
        await push_metrics(engine, writer, client, "https://ref.supabase.co", "chave")
        measures = await push_metrics(engine, writer, client, "https://ref.supabase.co", "chave")
    assert measures["supabase_metrics_up"] == 1
    # De 150 s de CPU entre as leituras, 50 ociosos: 2/3 ocupados.
    assert measures["supabase_cpu_utilization"] == pytest.approx(0.6667)
    assert "outbox_lag_seconds" in measures
    names = {series["metric"]["type"] for series in sent[-1]["timeSeries"]}
    assert "custom.googleapis.com/aid/supabase_cpu_utilization" in names


@pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
@pytest.mark.asyncio
async def test_sem_metrics_api_as_medidas_do_banco_saem_assim_mesmo(engine: AsyncEngine) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "metadata.google.internal":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if request.url.path == "/customer/v1/privileged/metrics":
            return httpx.Response(503)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        measures = await push_metrics(
            engine, MonitoringWriter("aid-test", client), client, "https://ref.supabase.co", "x"
        )
    assert measures["supabase_metrics_up"] == 0
    assert "diagnoses_queued" in measures
