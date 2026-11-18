"""Consumo do RabbitMQ pelos workers (Railway, ADR-0024) contra um broker real: o mesmo handler do
push do Pub/Sub, a confirmação só no sucesso, novas tentativas com espera e a DLQ depois da
quinta. Roda com AMQP_TEST_URL (job de integração do CI)."""

import asyncio
import base64
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import uuid4

import aio_pika
import httpx
import pytest
import pytest_asyncio
from aid_relay.rabbit import MAX_ATTEMPTS, RabbitPublisher, Topology
from aid_worker.main import PubSubMessage
from aid_worker.rabbit import Consumer

URL = os.environ.get("AMQP_TEST_URL")
pytestmark = [
    pytest.mark.skipif(URL is None, reason="sem AMQP_TEST_URL"),
    pytest.mark.asyncio,
]
TOPIC = "diagnosis.requested"


@pytest_asyncio.fixture
async def topology() -> AsyncIterator[Topology]:
    assert URL is not None
    created = Topology(namespace=f"test-{uuid4().hex[:8]}", delays=(1, 2))
    yield created
    connection = await aio_pika.connect(URL)
    async with connection:
        await created.delete(await connection.channel())


async def publish(topology: Topology, payload: object, attributes: dict[str, str]) -> None:
    assert URL is not None
    publisher = RabbitPublisher(URL, topology)
    async with httpx.AsyncClient() as client:
        await publisher.publish(client, TOPIC, [(json.dumps(payload).encode(), attributes)])
    await publisher.close()


async def until(check: Callable[[], bool], seconds: float = 15.0) -> None:
    for _ in range(int(seconds * 10)):
        if check():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("tempo esgotado")


async def run(topology: Topology, handler: Callable[[PubSubMessage], Awaitable[None]]) -> Consumer:
    assert URL is not None
    consumer = Consumer(URL, "diagnosis", {TOPIC: handler}, topology, prefetch=4)
    await consumer.start()
    return consumer


async def test_entrega_ao_handler_e_confirma(topology: Topology) -> None:
    received: list[PubSubMessage] = []

    async def handler(message: PubSubMessage) -> None:
        received.append(message)

    consumer = await run(topology, handler)
    await publish(topology, {"incident_id": "i"}, {"tenant_id": "t", "outbox_id": "9"})
    await until(lambda: len(received) == 1)
    await consumer.close()
    message = received[0]
    assert json.loads(base64.b64decode(message.data)) == {"incident_id": "i"}
    assert message.attributes == {"tenant_id": "t", "outbox_id": "9"}
    assert message.message_id == "9"
    assert URL is not None
    connection = await aio_pika.connect(URL)
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue(topology.queue(TOPIC), passive=True)
        assert queue.declaration_result.message_count == 0


async def test_falha_volta_depois_da_espera(topology: Topology) -> None:
    calls: list[str] = []

    async def handler(message: PubSubMessage) -> None:
        calls.append(message.message_id)
        if len(calls) == 1:
            raise RuntimeError("falha passageira")

    consumer = await run(topology, handler)
    await publish(topology, {}, {"outbox_id": "1"})
    await until(lambda: len(calls) == 2)
    await consumer.close()
    assert calls == ["1", "1"]


async def test_depois_da_quinta_falha_vai_para_a_dlq(topology: Topology) -> None:
    calls: list[str] = []

    async def handler(message: PubSubMessage) -> None:
        calls.append(message.message_id)
        raise RuntimeError("sempre falha")

    consumer = await run(topology, handler)
    await publish(topology, {"x": 1}, {"outbox_id": "5", "tenant_id": "t"})
    await until(lambda: len(calls) == MAX_ATTEMPTS, seconds=20)
    await asyncio.sleep(2.5)
    await consumer.close()
    assert len(calls) == MAX_ATTEMPTS
    assert URL is not None
    connection = await aio_pika.connect(URL)
    async with connection:
        channel = await connection.channel()
        dead = await channel.get_queue(topology.dead(TOPIC), ensure=False)
        message = await dead.get(no_ack=True, fail=False)
        assert message is not None
        assert json.loads(message.body) == {"x": 1}
        assert message.headers["tenant_id"] == "t"
        assert message.message_id == "5"
