"""Os tópicos do emulador são os do Terraform, e cada um ganha a assinatura push do worker."""

import json
import re
from pathlib import Path

import httpx
from aid_relay.emulator import TOPICS, ensure, setup

STACK = Path(__file__).resolve().parents[3] / "infrastructure/terraform/stack/main.tf"


def test_mesmos_topicos_e_workers_do_terraform() -> None:
    text = STACK.read_text(encoding="utf-8")
    found = {
        topic: (worker, int(ack))
        for topic, worker, ack in re.findall(
            r'"([a-z]+(?:\.[a-z]+)+)"\s*=\s*\{\s*worker\s*=\s*"(\w+)".*?ack_deadline\s*=\s*(\d+)',
            text,
        )
    }
    assert found == TOPICS


def test_cria_topico_e_assinatura_push_para_o_worker() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, json.loads(request.content or b"{}")))
        return httpx.Response(409 if "topics" in request.url.path else 200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        done = setup("http://pubsub:8085", "aid-local", "http://worker-{worker}:8080", client)
    assert len(done) == len(TOPICS)
    subscription = dict(calls)["/v1/projects/aid-local/subscriptions/diagnosis.requested.push"]
    assert subscription["pushConfig"] == {"pushEndpoint": "http://worker-diagnosis:8080/pubsub"}
    assert subscription["ackDeadlineSeconds"] == 600


def test_recria_so_quando_o_emulador_perdeu_os_topicos() -> None:
    puts: list[str] = []
    existing: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200, json={"topics": [{"name": f"projects/p/topics/{t}"} for t in existing]}
            )
        puts.append(request.url.path)
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert ensure("http://pubsub:8085", "p", "http://worker-{worker}:8080", client) == len(
            TOPICS
        )
        assert len(puts) == 2 * len(TOPICS)
        existing.extend(TOPICS)
        puts.clear()
        assert ensure("http://pubsub:8085", "p", "http://worker-{worker}:8080", client) == 0
        assert puts == []
