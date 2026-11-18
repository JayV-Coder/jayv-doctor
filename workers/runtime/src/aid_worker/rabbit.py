"""Consumo das filas do RabbitMQ (Railway, ADR-0024): cada worker consome as filas dos seus
tópicos e entrega ao mesmo handler do push do Pub/Sub.

Sucesso confirma a mensagem. Falha publica a mensagem na fila de espera da tentativa (ou, depois
da quinta, na DLQ do tópico) e só então confirma a original: a entrega continua pelo menos uma
vez, e os handlers já são idempotentes. Se o worker cair antes de confirmar, o broker reentrega."""

import base64
import logging
from collections.abc import Mapping

import aio_pika
from aid_relay.rabbit import ATTEMPT_HEADER, MAX_ATTEMPTS, Topology, amqp_message
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage, AbstractRobustConnection

from aid_worker.main import Handler, PubSubMessage, process

logger = logging.getLogger(__name__)
# Mensagens em processamento ao mesmo tempo por worker (no Cloud Run, a concorrência do serviço).
PREFETCH = 8


def attributes_of(message: AbstractIncomingMessage) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in (message.headers or {}).items()
        if key != ATTEMPT_HEADER and isinstance(value, str | bytes | int)
    }


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
        prefetch: int = PREFETCH,
    ) -> None:
        self.url = url
        self.worker = worker
        self.handlers = handlers
        self.topology = topology or Topology()
        self.prefetch = prefetch
        self.connection: AbstractRobustConnection | None = None
        self.channel: AbstractChannel | None = None

    async def start(self) -> None:
        self.connection = await aio_pika.connect_robust(self.url, timeout=10)
        self.channel = await self.connection.channel(publisher_confirms=True)
        await self.channel.set_qos(prefetch_count=self.prefetch)
        await self.topology.declare(self.channel)
        for topic, handler in self.handlers.items():
            queue = await self.channel.get_queue(self.topology.queue(topic), ensure=False)
            await queue.consume(self.on_message(topic, handler))
        logger.info("consumindo %d filas do RabbitMQ", len(self.handlers))

    def on_message(self, topic: str, handler: Handler):  # type: ignore[no-untyped-def]
        async def receive(message: AbstractIncomingMessage) -> None:
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
        if attempt >= MAX_ATTEMPTS:
            target = await self.channel.get_exchange(self.topology.dead_exchange, ensure=False)
            logger.warning("mensagem para a DLQ: topic=%s message_id=%s", topic, message.message_id)
        else:
            retry.headers[ATTEMPT_HEADER] = attempt + 1
            target = await self.channel.get_exchange(self.topology.retry(attempt), ensure=False)
        retry.message_id = message.message_id
        try:
            await target.publish(retry, routing_key=topic)
        except Exception:
            # Sem confirmar: o broker reentrega quando a conexão voltar.
            logger.exception("falha ao reagendar a mensagem")
            await message.nack(requeue=True)
            return
        await message.ack()

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
        self.connection = None
        self.channel = None
