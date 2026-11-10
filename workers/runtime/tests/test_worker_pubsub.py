import logging
from typing import Any

import pytest
from aid_worker.main import PubSubMessage, create_app
from fastapi.testclient import TestClient

ENVELOPE = {
    "message": {"data": "e30=", "messageId": "1", "attributes": {}},
    "subscription": "projects/aid/subscriptions/ingestion.raw.push",
}


def post(topic: str, received: list[str], json: object = ENVELOPE) -> Any:
    async def handler(message: PubSubMessage) -> None:
        received.append(message.message_id)

    return TestClient(create_app("ingestion", {topic: handler})).post("/pubsub", json=json)


def test_topico_sem_handler_responde_501_para_a_mensagem_nao_se_perder() -> None:
    assert post("correlation.requested", []).status_code == 501


def test_handler_e_escolhido_pelo_topico_da_assinatura() -> None:
    received: list[str] = []
    assert post("ingestion.raw", received).status_code == 204
    assert received == ["1"]


def test_envelope_invalido_nao_e_confirmado() -> None:
    received: list[str] = []
    assert post("ingestion.raw", received, {"subscription": "x"}).status_code == 422
    assert received == []


def test_worker_de_ingestao_registra_o_topico_ingestion_raw() -> None:
    from aid_worker.main import handlers_for

    assert set(handlers_for("ingestion")) == {"ingestion.raw"}
    assert set(handlers_for("diagnosis")) == {
        "rules.evaluate",
        "knowledge.index",
        "diagnosis.requested",
        "diagnosis.published",
        "usage.threshold",
        "report.requested",
        "incident.opened",
        "incident.updated",
    }
    assert handlers_for("desconhecido") == {}


def test_payload_json_chega_decodificado_ao_handler() -> None:
    import asyncio
    import base64
    import json

    from aid_worker.main import json_handler

    received: list[object] = []

    async def handler(payload: object) -> None:
        received.append(payload)

    data = base64.b64encode(json.dumps({"import_id": "abc"}).encode()).decode()

    async def deliver() -> None:
        await json_handler(handler)(PubSubMessage(messageId="1", data=data))

    asyncio.run(deliver())
    assert received == [{"import_id": "abc"}]


def test_so_o_relay_expoe_a_rota_do_scheduler(monkeypatch: Any) -> None:
    import aid_relay.handlers as relay
    from aid_relay.relay import Stats

    async def drain(*args: object, **kwargs: object) -> Stats:
        return Stats(published=3)

    monkeypatch.setattr(relay, "drain", drain)
    monkeypatch.setattr(relay, "engine", lambda: None)
    monkeypatch.setattr(relay, "publisher", lambda: None)
    response = TestClient(create_app("relay", {})).post("/relay")
    assert response.json() == {"published": 3, "failed": 0}
    assert TestClient(create_app("ingestion", {})).post("/relay").status_code == 404


def test_worker_de_conectores_registra_o_topico_e_o_agendador() -> None:
    from aid_worker.main import handlers_for

    assert set(handlers_for("connectors")) == {"connector.sync"}
    assert TestClient(create_app("ingestion", {})).post("/schedule").status_code == 404


def test_worker_de_alertas_registra_o_topico_e_a_varredura() -> None:
    from aid_worker.main import create_app as build
    from aid_worker.main import handlers_for, routers_for

    assert set(handlers_for("notifier")) == {"alert.evaluate"}
    paths = {route.path for router in routers_for("notifier") for route in router.routes}  # type: ignore[attr-defined]
    assert paths == {"/alerts/scan"}
    assert build("diagnosis", {}) is not None


def test_falha_do_handler_e_registrada_com_o_contexto_e_reentregue(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def handler(message: PubSubMessage) -> None:
        raise RuntimeError("banco fora")

    caplog.set_level(logging.ERROR)
    envelope = {
        "message": {"data": "e30=", "messageId": "1", "attributes": {"tenant_id": "t1"}},
        "subscription": "projects/aid/subscriptions/ingestion.raw.push",
    }
    response = TestClient(create_app("ingestion", {"ingestion.raw": handler})).post(
        "/pubsub", json=envelope
    )
    assert response.status_code == 500
    assert "falha ao processar a mensagem" in caplog.text
