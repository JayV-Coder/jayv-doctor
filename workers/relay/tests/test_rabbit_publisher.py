"""RabbitPublisher sem broker: recusa parcial de um lote e conexão que falha ao abrir."""

from typing import Any

import httpx
import pytest
from aid_relay.publisher import PublishError
from aid_relay.rabbit import RabbitPublisher, Topology
from aid_relay.relay import Stats, publish_batch
from aio_pika.exceptions import DeliveryError

pytestmark = pytest.mark.asyncio


class Exchange:
    """Recusa (nack) a mensagem com `outbox_id` 2; aceita as outras."""

    async def publish(self, message: Any, routing_key: str, mandatory: bool) -> None:
        if message.headers.get("outbox_id") == "2":
            raise DeliveryError(None, None)  # type: ignore[arg-type]


async def test_recusa_parcial_aponta_so_as_mensagens_recusadas() -> None:
    publisher = RabbitPublisher("amqp://x", Topology())
    publisher.exchange = Exchange()  # type: ignore[assignment]
    messages = [(b"{}", {"outbox_id": str(n)}) for n in (1, 2, 3)]
    async with httpx.AsyncClient() as client:
        with pytest.raises(PublishError) as error:
            await publisher.publish(client, "ingestion.raw", messages)
    assert error.value.rejected is True
    assert error.value.failed == {1}


async def test_relay_marca_publicadas_as_aceitas_de_um_lote_recusado_em_parte() -> None:
    publisher = RabbitPublisher("amqp://x", Topology())
    publisher.exchange = Exchange()  # type: ignore[assignment]
    rows = [
        type(
            "Row",
            (),
            {
                "id": n,
                "topic": "ingestion.raw",
                "payload": {},
                "tenant_id": "t",
                "traceparent": None,
            },
        )()
        for n in (1, 2, 3)
    ]
    async with httpx.AsyncClient() as client:
        published, rejected = await publish_batch(client, publisher, rows, Stats())
    assert published == [1, 3]
    assert rejected == [2]


class Connection:
    closed = 0

    async def channel(self, **_: Any) -> Any:
        raise ConnectionResetError("canal")

    async def close(self) -> None:
        Connection.closed += 1


async def test_falha_ao_abrir_fecha_a_conexao_em_vez_de_vazar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def connect(*_: Any, **__: Any) -> Connection:
        return Connection()

    monkeypatch.setattr("aid_relay.rabbit.aio_pika.connect_robust", connect)
    publisher = RabbitPublisher("amqp://x", Topology())
    async with httpx.AsyncClient() as client:
        for _ in range(2):
            with pytest.raises(PublishError):
                await publisher.publish(client, "ingestion.raw", [(b"{}", {})])
    assert Connection.closed == 2
    assert publisher.connection is None
