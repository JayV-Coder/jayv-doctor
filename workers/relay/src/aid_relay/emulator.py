"""Tópicos e assinaturas push no emulador do Pub/Sub, para rodar fora do GCP (Dokploy, stack
local). No GCP quem cria é o Terraform (`local.topics` em `infrastructure/terraform/stack`); um
teste confere que esta lista é a mesma.

    PUBSUB_EMULATOR_HOST=pubsub:8085 GCP_PROJECT_ID=aid-local \\
    AID_WORKER_URL=http://worker-{worker}:8080 python -m aid_relay.emulator
"""

import logging
import os
import sys

import httpx

log = logging.getLogger(__name__)
# Tópico → (worker que consome, prazo do ack em segundos), como no Terraform.
TOPICS: dict[str, tuple[str, int]] = {
    "ingestion.raw": ("ingestion", 300),
    "ingestion.normalized": ("correlation", 300),
    "correlation.requested": ("correlation", 300),
    "rules.evaluate": ("diagnosis", 600),
    "incident.opened": ("diagnosis", 600),
    "incident.updated": ("diagnosis", 600),
    "knowledge.index": ("diagnosis", 600),
    "diagnosis.requested": ("diagnosis", 600),
    "diagnosis.published": ("diagnosis", 600),
    "usage.threshold": ("diagnosis", 600),
    "report.requested": ("diagnosis", 600),
    "connector.sync": ("connectors", 600),
    "enrichment.requested": ("connectors", 600),
    "alert.evaluate": ("notifier", 300),
    "webhook.deliver": ("notifier", 300),
    "itsm.ticket": ("notifier", 300),
    "itsm.sync": ("notifier", 300),
    "itsm.comment": ("notifier", 300),
    "sso.domain": ("notifier", 300),
    "sso.sync": ("notifier", 300),
}


def setup(base: str, project: str, worker_url: str, client: httpx.Client) -> list[str]:
    """Cria (ou mantém) cada tópico e a assinatura `<tópico>.push` que entrega no worker."""
    done = []
    for topic, (worker, ack) in TOPICS.items():
        path = f"{base}/v1/projects/{project}"
        found = client.put(f"{path}/topics/{topic}", json={})
        if found.status_code not in (200, 409):
            found.raise_for_status()
        subscription = client.put(
            f"{path}/subscriptions/{topic}.push",
            json={
                "topic": f"projects/{project}/topics/{topic}",
                "pushConfig": {"pushEndpoint": f"{worker_url.format(worker=worker)}/pubsub"},
                "ackDeadlineSeconds": min(ack, 600),
            },
        )
        if subscription.status_code not in (200, 409):
            subscription.raise_for_status()
        done.append(topic)
    return done


def missing(base: str, project: str, client: httpx.Client) -> list[str]:
    """Tópicos que o emulador não tem (ele guarda tudo em memória e perde ao reiniciar)."""
    found = client.get(f"{base}/v1/projects/{project}/topics", params={"pageSize": 1000})
    found.raise_for_status()
    names = {t["name"].rsplit("/", 1)[-1] for t in found.json().get("topics", [])}
    return [topic for topic in TOPICS if topic not in names]


def ensure(base: str, project: str, worker_url: str, client: httpx.Client) -> int:
    """Recria tópicos e assinaturas se faltar algum; devolve quantos faltavam."""
    gone = missing(base, project, client)
    if gone:
        setup(base, project, worker_url, client)
        log.warning("emulador sem %d tópicos (reiniciou?): recriados", len(gone))
    return len(gone)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("PUBSUB_EMULATOR_HOST")
    if not host:
        log.error("PUBSUB_EMULATOR_HOST não definido: no GCP, os tópicos são do Terraform")
        return 2
    with httpx.Client(timeout=httpx.Timeout(15.0)) as client:
        done = setup(
            f"http://{host}",
            os.environ.get("GCP_PROJECT_ID", "aid-local"),
            os.environ.get("AID_WORKER_URL", "http://worker-{worker}:8080"),
            client,
        )
    log.info("%d tópicos com assinatura push no emulador", len(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
