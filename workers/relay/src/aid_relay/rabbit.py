"""O RabbitMQ no lugar do Pub/Sub fora do GCP (Railway, ADR-0024). No GCP continua o Pub/Sub do
Terraform; aqui a topologia reproduz o que as assinaturas de lá garantem:

- uma fila por tópico (`aid.<tópico>`), ligada à exchange `aid` pela routing key do tópico;
- cada mensagem tem até 5 tentativas (`max_delivery_attempts`): a falha volta à fila depois de
  uma espera crescente, pelas filas de espera `aid.retry.<n>s` (TTL e dead-letter de volta à
  exchange `aid`, com a mesma routing key);
- depois da quinta, a mensagem vai para `aid.dead.<tópico>`, onde fica 7 dias;
- se o worker cair no meio da mensagem, o broker reentrega; a fila quorum limita essas
  reentregas e manda à DLQ a mensagem que derruba o worker sempre.

Quem conecta declara tudo (relay e workers): a declaração é idempotente."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

import aio_pika
import httpx
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractQueue,
    AbstractRobustConnection,
)
from aiormq.exceptions import AMQPError

from aid_relay.emulator import TOPICS
from aid_relay.publisher import Message, PublishError

MAX_ATTEMPTS = 5
# Esperas entre as tentativas, como o backoff do Pub/Sub (de 10 s em diante).
RETRY_DELAYS = (10, 30, 90, 270)
DEAD_TTL_MS = 7 * 24 * 3600 * 1000
# Como a retenção do Pub/Sub: mensagem que ninguém consome em 7 dias vai para a DLQ, onde aparece.
QUEUE_TTL_MS = 7 * 24 * 3600 * 1000
ATTEMPT_HEADER = "x-aid-attempt"


class Declared(NamedTuple):
    exchange: AbstractExchange
    # Tópico → a fila declarada neste canal: consumir por ela deixa o canal robusto restaurar o
    # consumo depois de uma reconexão.
    queues: dict[str, AbstractQueue]


@dataclass(frozen=True)
class Topology:
    namespace: str = "aid"
    delays: tuple[int, ...] = RETRY_DELAYS
    topics: tuple[str, ...] = tuple(TOPICS)

    @property
    def exchange(self) -> str:
        return self.namespace

    @property
    def dead_exchange(self) -> str:
        return f"{self.namespace}.dead"

    def queue(self, topic: str) -> str:
        return f"{self.namespace}.{topic}"

    def dead(self, topic: str) -> str:
        return f"{self.namespace}.dead.{topic}"

    def retry(self, attempt: int) -> str:
        """Fila de espera depois da tentativa `attempt` (1 = a primeira falhou)."""
        return f"{self.namespace}.retry.{self.delays[min(attempt, len(self.delays)) - 1]}s"

    async def declare(self, channel: AbstractChannel) -> Declared:
        exchange = await channel.declare_exchange(
            self.exchange, aio_pika.ExchangeType.DIRECT, durable=True
        )
        dead = await channel.declare_exchange(
            self.dead_exchange, aio_pika.ExchangeType.DIRECT, durable=True
        )
        queues: dict[str, AbstractQueue] = {}
        for topic in self.topics:
            queue = await channel.declare_queue(
                self.queue(topic),
                durable=True,
                arguments={
                    "x-queue-type": "quorum",
                    # Reentregas por queda do worker (sem ack); as falhas tratadas usam as
                    # filas de espera e não contam aqui.
                    "x-delivery-limit": MAX_ATTEMPTS,
                    "x-dead-letter-exchange": self.dead_exchange,
                    "x-message-ttl": QUEUE_TTL_MS,
                },
            )
            await queue.bind(exchange, routing_key=topic)
            queues[topic] = queue
            dlq = await channel.declare_queue(
                self.dead(topic), durable=True, arguments={"x-message-ttl": DEAD_TTL_MS}
            )
            await dlq.bind(dead, routing_key=topic)
        for seconds in sorted(set(self.delays)):
            name = f"{self.namespace}.retry.{seconds}s"
            wait = await channel.declare_exchange(name, aio_pika.ExchangeType.FANOUT, durable=True)
            # Sem `x-dead-letter-routing-key`: a mensagem volta com a routing key do tópico.
            queue = await channel.declare_queue(
                name,
                durable=True,
                arguments={
                    "x-message-ttl": seconds * 1000,
                    "x-dead-letter-exchange": self.exchange,
                },
            )
            await queue.bind(wait)
        return Declared(exchange, queues)

    async def delete(self, channel: AbstractChannel) -> None:
        """Só para testes: apaga o que `declare` criou."""
        for topic in self.topics:
            await channel.queue_delete(self.queue(topic))
            await channel.queue_delete(self.dead(topic))
        for seconds in sorted(set(self.delays)):
            await channel.queue_delete(f"{self.namespace}.retry.{seconds}s")
            await channel.exchange_delete(f"{self.namespace}.retry.{seconds}s")
        await channel.exchange_delete(self.exchange)
        await channel.exchange_delete(self.dead_exchange)


def amqp_message(data: bytes, attributes: dict[str, str]) -> aio_pika.Message:
    return aio_pika.Message(
        body=data,
        headers=dict(attributes),
        message_id=attributes.get("outbox_id"),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )


class RabbitPublisher:
    """Mesma interface do `PubSubPublisher` (o `client` HTTP não é usado). Cada mensagem sai com
    `mandatory` e confirmação do broker: sem fila para o tópico, ela volta e conta tentativa."""

    def __init__(self, url: str, topology: Topology) -> None:
        self.url = url
        self.topology = topology
        self.connection: AbstractRobustConnection | None = None
        self.exchange: AbstractExchange | None = None
        self.lock = asyncio.Lock()

    async def ready(self) -> AbstractExchange:
        async with self.lock:
            if self.exchange is None:
                connection = await aio_pika.connect_robust(self.url, timeout=10)
                try:
                    channel = await connection.channel(
                        publisher_confirms=True, on_return_raises=True
                    )
                    self.exchange = (await self.topology.declare(channel)).exchange
                except BaseException:
                    # Sem isso, cada rodada abriria uma conexão nova e deixaria a anterior
                    # tentando reconectar para sempre.
                    await connection.close()
                    raise
                self.connection = connection
            return self.exchange

    async def publish(
        self, client: httpx.AsyncClient, topic: str, messages: Sequence[Message]
    ) -> None:
        del client
        try:
            exchange = await self.ready()
        except (TimeoutError, OSError, AMQPError) as exc:
            raise PublishError(f"{topic}: broker indisponível", rejected=False) from exc
        results = await asyncio.gather(
            *(
                exchange.publish(
                    amqp_message(data, dict(attributes)), routing_key=topic, mandatory=True
                )
                for data, attributes in messages
            ),
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, BaseException)]
        if not errors:
            return
        unexpected = [
            error for error in errors if not isinstance(error, aio_pika.exceptions.DeliveryError)
        ]
        if unexpected:
            # Conexão ou broker: a rodada para sem gastar tentativa; o que já saiu sai de novo
            # na próxima (pelo menos uma vez).
            raise PublishError(
                f"{topic}: {type(unexpected[0]).__name__}", rejected=False
            ) from unexpected[0]
        # Voltou (sem fila para o tópico) ou o broker recusou (nack): só essas contam tentativa.
        failed = {n for n, result in enumerate(results) if isinstance(result, BaseException)}
        raise PublishError(
            f"{topic}: {len(failed)} recusadas pelo broker", rejected=True, failed=failed
        ) from errors[0]

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
        self.connection = None
        self.exchange = None
