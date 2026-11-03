from typing import Any

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
    assert handlers_for("diagnosis") == {}


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
