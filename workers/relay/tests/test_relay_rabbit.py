"""Relay contra Postgres real e o RabbitMQ (Railway, ADR-0024). Roda com INTEGRATION_DB_URL e
AMQP_TEST_URL (job de integração do CI)."""

import json
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import aio_pika
import pytest
import pytest_asyncio
from aid_relay.rabbit import RabbitPublisher, Topology
from aid_relay.relay import drain
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

DB = os.environ.get("INTEGRATION_DB_URL")
URL = os.environ.get("AMQP_TEST_URL")
pytestmark = [
    pytest.mark.skipif(DB is None or URL is None, reason="sem INTEGRATION_DB_URL e AMQP_TEST_URL"),
    pytest.mark.asyncio,
]


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert DB is not None
    created = create_async_engine(
        DB.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


@pytest_asyncio.fixture
async def tenant(engine: AsyncEngine) -> AsyncIterator[str]:
    tenant_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text("insert into public.organizations (id, name, slug) values (:t, 'T', :s)"),
            {"t": tenant_id, "s": f"t-{tenant_id[:30]}"},
        )
        await connection.execute(
            text("insert into doctor.tenants (id) values (:t)"), {"t": tenant_id}
        )
    yield tenant_id
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from doctor.outbox_messages where tenant_id = :t"), {"t": tenant_id}
        )
        await connection.execute(text("delete from doctor.tenants where id = :t"), {"t": tenant_id})
        await connection.execute(
            text("delete from public.organizations where id = :t"), {"t": tenant_id}
        )


def letters() -> str:
    """O nome do tópico na outbox não aceita dígitos."""
    return "".join(chr(ord("a") + int(char, 16)) for char in uuid4().hex[:10])


@pytest_asyncio.fixture
async def topology() -> AsyncIterator[Topology]:
    assert URL is not None
    created = Topology(
        namespace=f"test-{letters()}", delays=(1,), topics=(f"relay.test.{letters()}",)
    )
    yield created
    connection = await aio_pika.connect(URL)
    async with connection:
        await created.delete(await connection.channel())


async def enqueue(engine: AsyncEngine, tenant: str, topic: str) -> int:
    async with engine.begin() as connection:
        return int(
            await connection.scalar(
                text(
                    "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                    " values (:t, :topic, cast(:p as jsonb)) returning id"
                ),
                {"t": tenant, "topic": topic, "p": json.dumps({"import_id": "abc"})},
            )
        )


async def state(engine: AsyncEngine, message_id: int) -> tuple[bool, int]:
    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    "select published_at is not null as published, attempts"
                    " from doctor.outbox_messages where id = :i"
                ),
                {"i": message_id},
            )
        ).one()
    return row.published, row.attempts


async def test_publica_na_fila_e_marca_publicada(
    engine: AsyncEngine, tenant: str, topology: Topology
) -> None:
    assert URL is not None
    topic = topology.topics[0]
    message_id = await enqueue(engine, tenant, topic)
    publisher = RabbitPublisher(URL, topology)
    await drain(engine, publisher)
    await publisher.close()

    assert await state(engine, message_id) == (True, 0)
    connection = await aio_pika.connect(URL)
    async with connection:
        queue = await (await connection.channel()).get_queue(topology.queue(topic), ensure=False)
        message = await queue.get(no_ack=True)
        assert json.loads(message.body) == {"import_id": "abc"}
        assert message.headers["tenant_id"] == tenant
        assert message.headers["outbox_id"] == str(message_id)


async def test_topico_sem_fila_conta_tentativa_e_fica_na_outbox(
    engine: AsyncEngine, tenant: str, topology: Topology
) -> None:
    assert URL is not None
    message_id = await enqueue(engine, tenant, f"relay.semfila.{letters()}")
    publisher = RabbitPublisher(URL, topology)
    await drain(engine, publisher)
    await publisher.close()
    assert await state(engine, message_id) == (False, 1)
