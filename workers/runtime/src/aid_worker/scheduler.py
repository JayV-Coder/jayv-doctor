"""Os jobs do Cloud Scheduler fora do GCP (Dokploy, stack local): a cada minuto, chama as rotas
dos workers cujo horário bate. No GCP quem agenda é o Terraform (`google_cloud_scheduler_job`);
um teste confere que estes horários são os de lá. Ficam de fora o envio de métricas ao Cloud
Monitoring e o backup do Storage no GCS, que dependem do GCP.

Com o emulador do Pub/Sub (`PUBSUB_EMULATOR_HOST`), confere a cada minuto, antes dos jobs, se
os tópicos e as assinaturas push existem e recria o que faltar: o emulador guarda tudo em memória
e perde ao reiniciar, e o relay publicaria em tópicos que não existem.

    AID_WORKER_URL=http://worker-{worker}:8080 python -m aid_worker.scheduler
"""

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from aid_relay import emulator

log = logging.getLogger(__name__)
# (cron em UTC, worker, rota)
JOBS: list[tuple[str, str, str]] = [
    ("* * * * *", "relay", "/relay"),
    ("* * * * *", "connectors", "/schedule"),
    ("* * * * *", "correlation", "/close"),
    ("* * * * *", "notifier", "/alerts/scan"),
    ("*/5 * * * *", "diagnosis", "/enrichment/expire"),
    ("*/10 * * * *", "correlation", "/stats"),
    ("17 * * * *", "diagnosis", "/knowledge/reindex"),
    ("0 6 * * *", "diagnosis", "/retention/run"),
    ("15 6 * * *", "diagnosis", "/ai/verify"),
    ("40 3 * * *", "correlation", "/audit/auth-events"),
]
TIMEOUT = httpx.Timeout(600.0)


def field_matches(spec: str, value: int) -> bool:
    if spec == "*":
        return True
    if spec.startswith("*/"):
        return value % int(spec[2:]) == 0
    return any(int(part) == value for part in spec.split(","))


def due(cron: str, at: datetime) -> bool:
    """Cron de 5 campos com `*`, `*/n` e números (o que os jobs usam)."""
    minute, hour, day, month, weekday = cron.split()
    return (
        field_matches(minute, at.minute)
        and field_matches(hour, at.hour)
        and field_matches(day, at.day)
        and field_matches(month, at.month)
        and field_matches(weekday, (at.weekday() + 1) % 7)
    )


async def fire(client: httpx.AsyncClient, url: str) -> None:
    try:
        response = await client.post(url)
        log.info("job %s: HTTP %s", url, response.status_code)
    except httpx.HTTPError as exc:
        log.warning("job %s falhou: %s", url, type(exc).__name__)


def ensure_topics(worker_url: str) -> None:
    host = os.environ.get("PUBSUB_EMULATOR_HOST")
    if not host:
        return
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
            emulator.ensure(
                f"http://{host}", os.environ.get("GCP_PROJECT_ID", "aid-local"), worker_url, client
            )
    except httpx.HTTPError as exc:
        log.warning("emulador do Pub/Sub indisponível: %s", type(exc).__name__)


async def loop(worker_url: str) -> None:
    running: set[asyncio.Task[None]] = set()
    await asyncio.to_thread(ensure_topics, worker_url)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while True:
            now = datetime.now(UTC)
            following = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            await asyncio.sleep((following - now).total_seconds())
            await asyncio.to_thread(ensure_topics, worker_url)
            # Cada job em paralelo, sem segurar o minuto seguinte.
            for cron, worker, path in JOBS:
                if due(cron, following):
                    task = asyncio.create_task(
                        fire(client, worker_url.format(worker=worker) + path)
                    )
                    running.add(task)
                    task.add_done_callback(running.discard)


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    asyncio.run(loop(os.environ.get("AID_WORKER_URL", "http://worker-{worker}:8080")))


if __name__ == "__main__":
    main()
