"""Relay contra Postgres real e o emulador do Pub/Sub. Roda com INTEGRATION_DB_URL e
PUBSUB_EMULATOR_HOST (job de E2E do CI)."""

import asyncio
import base64
import json
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aid_relay.publisher import PubSubPublisher
from aid_relay.relay import drain
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

DB = os.environ.get("INTEGRATION_DB_URL")
EMULATOR = os.environ.get("PUBSUB_EMULATOR_HOST")
PROJECT = "aid-local"
pytestmark = pytest.mark.skipif(
    DB is None or EMULATOR is None, reason="sem INTEGRATION_DB_URL e PUBSUB_EMULATOR_HOST"
)


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
    """Sufixo aleatório só com letras: o nome do tópico na outbox não aceita dígitos."""
    return "".join(chr(ord("a") + int(char, 16)) for char in uuid4().hex[:10])


def emulator(path: str) -> str:
    return f"http://{EMULATOR}/v1/projects/{PROJECT}/{path}"


async def topic_with_subscription(name: str) -> str:
    async with httpx.AsyncClient() as client:
        await client.put(emulator(f"topics/{name}"))
        await client.put(
            emulator(f"subscriptions/{name}.test"),
            json={"topic": f"projects/{PROJECT}/topics/{name}"},
        )
    return f"{name}.test"


async def pull(subscription: str, expected: int = 1) -> list[dict[str, Any]]:
    """Puxa até ter `expected` mensagens (ou 10 s): um pull pode devolver menos que o disponível."""
    messages: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for _ in range(50):
            response = await client.post(
                emulator(f"subscriptions/{subscription}:pull"), json={"maxMessages": 100}
            )
            received = response.json().get("receivedMessages", [])
            messages += [item["message"] for item in received]
            if received:
                await client.post(
                    emulator(f"subscriptions/{subscription}:acknowledge"),
                    json={"ackIds": [item["ackId"] for item in received]},
                )
            if len(messages) >= expected:
                break
            await asyncio.sleep(0.2)
    return messages


async def enqueue(engine: AsyncEngine, tenant: str, topic: str, payload: dict[str, Any]) -> int:
    async with engine.begin() as connection:
        return int(
            await connection.scalar(
                text(
                    "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                    " values (:t, :topic, cast(:p as jsonb)) returning id"
                ),
                {"t": tenant, "topic": topic, "p": json.dumps(payload)},
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


def publisher() -> PubSubPublisher:
    return PubSubPublisher(PROJECT, emulator_host=EMULATOR)


@pytest.mark.asyncio
async def test_publica_com_o_tenant_nos_atributos_e_marca_publicada(
    engine: AsyncEngine, tenant: str
) -> None:
    topic = f"relay.test.{letters()}"
    subscription = await topic_with_subscription(topic)
    message_id = await enqueue(engine, tenant, topic, {"import_id": "abc"})

    await drain(engine, publisher())

    assert await state(engine, message_id) == (True, 0)
    received = [
        message
        for message in await pull(subscription)
        if message["attributes"]["outbox_id"] == str(message_id)
    ]
    assert len(received) == 1
    assert json.loads(base64.b64decode(received[0]["data"])) == {"import_id": "abc"}
    assert received[0]["attributes"]["tenant_id"] == tenant


@pytest.mark.asyncio
async def test_falha_de_publicacao_conta_tentativa_e_fica_na_fila(
    engine: AsyncEngine, tenant: str
) -> None:
    message_id = await enqueue(engine, tenant, f"relay.semtopico.{letters()}", {"x": 1})
    await drain(engine, publisher())
    assert await state(engine, message_id) == (False, 1)


@pytest.mark.asyncio
async def test_dois_relays_ao_mesmo_tempo_publicam_cada_mensagem_uma_vez(
    engine: AsyncEngine, tenant: str
) -> None:
    topic = f"relay.test.{letters()}"
    subscription = await topic_with_subscription(topic)
    ids = {str(await enqueue(engine, tenant, topic, {"n": n})) for n in range(30)}

    await asyncio.gather(drain(engine, publisher(), batch=5), drain(engine, publisher(), batch=5))

    received = [
        message["attributes"]["outbox_id"]
        for message in await pull(subscription, expected=len(ids))
        if message["attributes"]["outbox_id"] in ids
    ]
    assert sorted(received) == sorted(ids)


class Down(PubSubPublisher):
    async def publish(self, client: Any, topic: str, messages: Any) -> None:
        from aid_relay.publisher import PublishError

        raise PublishError(f"{topic}: HTTP 503", rejected=False)


@pytest.mark.asyncio
async def test_queda_do_pub_sub_nao_gasta_tentativa(engine: AsyncEngine, tenant: str) -> None:
    message_id = await enqueue(engine, tenant, f"relay.test.{letters()}", {"x": 1})
    stats = await drain(engine, Down(PROJECT, emulator_host=EMULATOR))
    assert stats.stopped
    assert await state(engine, message_id) == (False, 0)
