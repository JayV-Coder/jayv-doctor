"""Métricas da plataforma a cada minuto (ticket #34), pelo Cloud Scheduler: as medidas do banco
(`doctor.platform_health`) e a CPU e o disco do Supabase (Metrics API, com a chave de serviço
que só este worker e o de ingestão têm), gravadas no Cloud Monitoring."""

import json
import logging
import re
from collections.abc import Mapping
from typing import Any

import httpx
from aid_db import platform_role
from aid_observability.metrics import MonitoringWriter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

JOB = "supabase_metrics"
SAMPLE = re.compile(r"^(?P<name>[a-z_:]+)(?:\{(?P<labels>[^}]*)\})?\s+(?P<value>[-+0-9.eE]+|NaN)$")
LABEL = re.compile(r'(\w+)="([^"]*)"')
log = logging.getLogger(__name__)


def parse(body: str) -> list[tuple[str, dict[str, str], float]]:
    samples = []
    for line in body.splitlines():
        found = SAMPLE.match(line.strip())
        if found and found["value"] != "NaN":
            labels = dict(LABEL.findall(found["labels"] or ""))
            samples.append((found["name"], labels, float(found["value"])))
    return samples


def value_of(
    samples: list[tuple[str, dict[str, str], float]], name: str, mount: str
) -> float | None:
    return next(
        (v for n, labels, v in samples if n == name and labels.get("mountpoint") == mount), None
    )


def cpu_and_disk(
    samples: list[tuple[str, dict[str, str], float]], previous: Mapping[str, Any]
) -> tuple[dict[str, float], dict[str, float]]:
    """(medidas, contadores para a próxima rodada). A CPU sai da diferença entre duas leituras do
    contador `node_cpu_seconds_total` (a anterior fica em `platform_jobs`)."""
    cpu = [(labels, v) for n, labels, v in samples if n == "node_cpu_seconds_total"]
    idle = sum(v for labels, v in cpu if labels.get("mode") == "idle")
    total = sum(v for _, v in cpu)
    measures: dict[str, float] = {}
    if previous.get("total") is not None and total > float(previous["total"]):
        busy = 1 - (idle - float(previous["idle"])) / (total - float(previous["total"]))
        measures["supabase_cpu_utilization"] = round(min(1.0, max(0.0, busy)), 4)
    for mount in ("/data", "/"):
        size = value_of(samples, "node_filesystem_size_bytes", mount)
        free = value_of(samples, "node_filesystem_avail_bytes", mount)
        if size and free is not None:
            measures["supabase_disk_utilization"] = round(1 - free / size, 4)
            break
    return measures, {"idle": idle, "total": total}


async def supabase_measures(
    engine: AsyncEngine, client: httpx.AsyncClient, url: str, service_key: str
) -> dict[str, float]:
    response = await client.get(
        f"{url.rstrip('/')}/customer/v1/privileged/metrics", auth=("service_role", service_key)
    )
    response.raise_for_status()
    async with engine.begin() as connection:
        await platform_role(connection)
        previous = await connection.scalar(
            text("select details from doctor.platform_jobs where name = :n"), {"n": JOB}
        )
        measures, counters = cpu_and_disk(parse(response.text), previous or {})
        await connection.execute(
            text(
                "insert into doctor.platform_jobs (name, last_success_at, details)"
                " values (:n, now(), cast(:d as jsonb)) on conflict (name) do update"
                " set last_success_at = excluded.last_success_at, details = excluded.details"
            ),
            {"n": JOB, "d": json.dumps(counters)},
        )
    return measures


async def platform_measures(engine: AsyncEngine) -> dict[str, float]:
    async with engine.begin() as connection:
        await platform_role(connection)
        found = await connection.scalar(text("select doctor.platform_health()"))
    return {name: float(value) for name, value in dict(found or {}).items()}


async def push_metrics(
    engine: AsyncEngine,
    writer: MonitoringWriter,
    client: httpx.AsyncClient,
    supabase_url: str,
    service_key: str,
) -> dict[str, float]:
    measures = await platform_measures(engine)
    try:
        measures.update(await supabase_measures(engine, client, supabase_url, service_key))
        measures["supabase_metrics_up"] = 1
    except (httpx.HTTPError, ValueError):
        # Sem a Metrics API, o resto das medidas sai assim mesmo; o alerta de CPU fica sem dado.
        log.warning("Metrics API do Supabase indisponível")
        measures["supabase_metrics_up"] = 0
    await writer.gauges(measures)
    return measures
