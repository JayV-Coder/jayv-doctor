"""Consumo das filas do RabbitMQ (Railway, ADR-0024): cada worker consome as filas dos seus
tópicos e entrega ao mesmo handler do push do Pub/Sub.

Sucesso confirma a mensagem. Falha publica a mensagem na fila de espera da tentativa (ou, depois
da quinta, na DLQ do tópico) e só então confirma a original: a entrega continua pelo menos uma
vez, e os handlers já são idempotentes. Se o worker cair antes de confirmar, o broker reentrega."""

import asyncio
import base64
import logging
import math
from collections.abc import Awaitable, Callable, Mapping

import aio_pika
from aid_relay.rabbit import ATTEMPT_HEADER, MAX_ATTEMPTS, Topology, amqp_message
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractRobustConnection

from aid_worker.main import Handler, PubSubMessage, process

logger = logging.getLogger(__name__)
# Mensagens em processamento ao mesmo tempo no worker inteiro, somadas todas as filas (no Cloud
# Run, a concorrência do serviço; o orçamento de conexões do Supavisor conta com ela).
CONCURRENCY = 8
# Se nem a fila de espera aceita a mensagem, ela volta à fila do tópico depois deste tempo.
REQUEUE_SECONDS = 10.0


def attributes_of(message: AbstractIncomingMessage) -> dict[str, str]:
    """Os atributos da outbox, como no Pub/Sub. Ficam de fora os cabeçalhos do broker (`x-death`,
    `x-first-death-*`…), o da tentativa e o que não for texto."""
    attributes: dict[str, str] = {}
    for key, value in (message.headers or {}).items():
        if key.startswith("x-"):
            continue
        if isinstance(value, str):
            attributes[key] = value
        elif isinstance(value, bytes):
            attributes[key] = value.decode("utf-8", errors="replace")
    return attributes


def attempt_of(message: AbstractIncomingMessage) -> int:
    """Tentativa desta entrega (1 na primeira); cabeçalho ausente ou estranho conta como 1."""
    value = (message.headers or {}).get(ATTEMPT_HEADER)
    return value if isinstance(value, int) and value > 0 else 1


class Consumer:
    def __init__(
        self,
        url: str,
        worker: str,
        handlers: Mapping[str, Handler],
        topology: Topology | None = None,
        *,
        prefetch: int = CONCURRENCY,
    ) -> None:
        self.url = url
        self.worker = worker
        self.handlers = handlers
        self.topology = topology or Topology()
        self.slots = asyncio.Semaphore(prefetch)
        # O prefetch do RabbitMQ vale por consumidor (as filas quorum não aceitam o do canal):
        # dividido entre as filas, o worker não segura mais mensagens do que processa.
        self.prefetch = max(1, math.ceil(prefetch / max(1, len(handlers))))
        self.connection: AbstractRobustConnection | None = None
        self.channel: AbstractChannel | None = None

    async def start(self) -> None:
        self.connection = await aio_pika.connect_robust(self.url, timeout=10)
        self.channel = await self.connection.channel(publisher_confirms=True)
        await self.channel.set_qos(prefetch_count=self.prefetch)
        declared = await self.topology.declare(self.channel)
        for topic, handler in self.handlers.items():
            # A fila que o canal robusto registrou: na reconexão, ele refaz o consumo dela.
            await declared.queues[topic].consume(self.on_message(topic, handler))
        logger.info("consumindo %d filas do RabbitMQ", len(self.handlers))

    @property
    def healthy(self) -> bool:
        return (
            self.connection is not None
            and not self.connection.is_closed
            and self.channel is not None
            and not self.channel.is_closed
        )

    def on_message(
        self, topic: str, handler: Handler
    ) -> Callable[[AbstractIncomingMessage], Awaitable[None]]:
        async def receive(message: AbstractIncomingMessage) -> None:
            async with self.slots:
                envelope = PubSubMessage(
                    messageId=message.message_id or "",
                    data=base64.b64encode(message.body).decode(),
                    attributes=attributes_of(message),
                )
                if await process(self.worker, topic, envelope, handler):
                    await message.ack()
                    return
                await self.again(topic, message, envelope.attributes)

        return receive

    async def again(
        self, topic: str, message: AbstractIncomingMessage, attributes: dict[str, str]
    ) -> None:
        if self.channel is None:
            return
        attempt = attempt_of(message)
        retry = amqp_message(message.body, attributes)
        retry.message_id = message.message_id
        try:
            if attempt >= MAX_ATTEMPTS:
                target = await self.channel.get_exchange(self.topology.dead_exchange, ensure=False)
                logger.warning(
                    "mensagem para a DLQ: topic=%s message_id=%s", topic, message.message_id
                )
            else:
                retry.headers[ATTEMPT_HEADER] = attempt + 1
                target = await self.channel.get_exchange(self.topology.retry(attempt), ensure=False)
            await target.publish(retry, routing_key=topic)
        except Exception:
            # Sem a fila de espera, a mensagem volta à do tópico, mas não na hora: repetir o
            # handler sem espera gastaria as reentregas da fila quorum em segundos.
            logger.exception("falha ao reagendar a mensagem")
            await asyncio.sleep(REQUEUE_SECONDS)
            try:
                await message.nack(requeue=True)
            except Exception:
                # Canal fechado: o broker já devolveu a mensagem à fila.
                logger.warning("canal fechado ao devolver a mensagem: topic=%s", topic)
            return
        await message.ack()

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
        self.connection = None
        self.channel = None
