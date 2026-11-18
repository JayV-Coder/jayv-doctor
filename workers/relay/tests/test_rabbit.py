"""Publicação no RabbitMQ (Railway, ADR-0024) contra um broker real. Roda com AMQP_TEST_URL
(job de integração do CI). Cada teste usa um namespace próprio e apaga o que declarou."""

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import aio_pika
import httpx
import pytest
import pytest_asyncio
from aid_relay.emulator import TOPICS
from aid_relay.publisher import PublishError
from aid_relay.rabbit import RabbitPublisher, Topology

URL = os.environ.get("AMQP_TEST_URL")
pytestmark = [
    pytest.mark.skipif(URL is None, reason="sem AMQP_TEST_URL"),
    pytest.mark.asyncio,
]


@pytest_asyncio.fixture
async def topology() -> AsyncIterator[Topology]:
    assert URL is not None
    created = Topology(namespace=f"test-{uuid4().hex[:8]}", delays=(1, 2))
    yield created
    connection = await aio_pika.connect(URL)
    async with connection:
        channel = await connection.channel()
        await created.delete(channel)


async def get(channel: aio_pika.abc.AbstractChannel, queue: str) -> aio_pika.IncomingMessage:
    found = await channel.get_queue(queue, ensure=False)
    for _ in range(50):
        message = await found.get(no_ack=True, fail=False)
        if message is not None:
            return message  # type: ignore[return-value]
        await asyncio.sleep(0.1)
    raise AssertionError(f"nada na fila {queue}")


async def test_publica_na_fila_do_topico_com_os_atributos(topology: Topology) -> None:
    assert URL is not None
    publisher = RabbitPublisher(URL, topology)
    async with httpx.AsyncClient() as client:
        await publisher.publish(
            client,
            "diagnosis.requested",
            [(b'{"incident_id": "i"}', {"tenant_id": "t", "outbox_id": "7"})],
        )
    await publisher.close()
    connection = await aio_pika.connect(URL)
    async with connection:
        channel = await connection.channel()
        message = await get(channel, topology.queue("diagnosis.requested"))
        assert message.body == b'{"incident_id": "i"}'
        assert message.headers == {"tenant_id": "t", "outbox_id": "7"}
        assert message.message_id == "7"
        assert message.delivery_mode == aio_pika.DeliveryMode.PERSISTENT


async def test_declara_uma_fila_por_topico_e_a_dlq_de_cada(topology: Topology) -> None:
    assert URL is not None
    publisher = RabbitPublisher(URL, topology)
    async with httpx.AsyncClient() as client:
        await publisher.publish(client, "ingestion.raw", [(b"{}", {})])
    await publisher.close()
    connection = await aio_pika.connect(URL)
    async with connection:
        channel = await connection.channel()
        for topic in TOPICS:
            # `passive`: falha se não existir.
            await channel.declare_queue(topology.queue(topic), passive=True)
            await channel.declare_queue(topology.dead(topic), passive=True)


async def test_topico_desconhecido_e_recusado_e_conta_tentativa(topology: Topology) -> None:
    assert URL is not None
    publisher = RabbitPublisher(URL, topology)
    async with httpx.AsyncClient() as client:
        with pytest.raises(PublishError) as error:
            await publisher.publish(client, "nao.existe", [(b"{}", {})])
    await publisher.close()
    assert error.value.rejected is True


async def test_broker_fora_do_ar_nao_gasta_tentativa() -> None:
    publisher = RabbitPublisher("amqp://guest:guest@127.0.0.1:1/", Topology())
    async with httpx.AsyncClient() as client:
        with pytest.raises(PublishError) as error:
            await publisher.publish(client, "ingestion.raw", [(b"{}", {})])
    assert error.value.rejected is False
