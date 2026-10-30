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
