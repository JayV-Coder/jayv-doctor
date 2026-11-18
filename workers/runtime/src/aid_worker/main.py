"""Recebe o push autenticado do Pub/Sub (GCP) ou consome o RabbitMQ (Railway, ADR-0024) e
entrega ao handler do worker.

Qualquer resposta fora de 2xx faz o Pub/Sub reentregar a mensagem e, depois de 5 tentativas,
movê-la para a DLQ. Por isso worker sem handler responde 501 em vez de confirmar: confirmar
descartaria a mensagem. A validação do OIDC é do Cloud Run, com o `run.invoker` do Terraform.
"""

import base64
import json
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any

from aid_observability import logs, tracing
from aid_observability.logs import bind
from aid_observability.tracing import context_from, tracer
from fastapi import APIRouter, FastAPI, Response, status
from opentelemetry.trace import SpanKind
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class PubSubMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: str = Field(alias="messageId")
    data: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)


class PushEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str


Handler = Callable[[PubSubMessage], Awaitable[None]]

PayloadHandler = Callable[[Mapping[str, Any]], Awaitable[None]]


def json_handler(handler: PayloadHandler) -> Handler:
    """O `data` do Pub/Sub é o JSON da outbox em base64. Inválido sobe como erro: a mensagem é
    reentregue e, depois de 5 tentativas, vai para a DLQ, onde fica visível."""

    async def handle(message: PubSubMessage) -> None:
        await handler(json.loads(base64.b64decode(message.data)))

    return handle


def handlers_for(worker: str) -> dict[str, Handler]:
    """Chave: nome do tópico. Um worker pode receber mais de um, com formatos diferentes. Cada
    worker importa só o próprio pacote: a mesma imagem serve a todos (WORKER_NAME)."""
    if worker == "ingestion":
        from aid_ingestion.handlers import TOPICS

        return {topic: json_handler(handler) for topic, handler in TOPICS.items()}
    if worker == "connectors":
        from aid_connector_worker.handlers import TOPICS as CONNECTOR_TOPICS

        return {topic: json_handler(handler) for topic, handler in CONNECTOR_TOPICS.items()}
    if worker == "correlation":
        from aid_correlation_worker.handlers import TOPICS as CORRELATION_TOPICS

        return {topic: json_handler(handler) for topic, handler in CORRELATION_TOPICS.items()}
    if worker == "diagnosis":
        from aid_diagnosis_worker.handlers import TOPICS as DIAGNOSIS_TOPICS

        return {topic: json_handler(handler) for topic, handler in DIAGNOSIS_TOPICS.items()}
    if worker == "notifier":
        from aid_notifier.handlers import TOPICS as NOTIFIER_TOPICS

        return {topic: json_handler(handler) for topic, handler in NOTIFIER_TOPICS.items()}
    return {}


def topic_of(subscription: str) -> str:
    """`projects/x/subscriptions/ingestion.raw.push` => `ingestion.raw` (ver Terraform)."""
    return subscription.rsplit("/", 1)[-1].removesuffix(".push")


def routers_for(worker: str) -> list[APIRouter]:
    """Rotas próprias de um worker que não vêm do Pub/Sub (ex.: o relay, chamado pelo Scheduler)."""
    if worker == "relay":
        from aid_relay.handlers import router

        return [router]
    if worker == "connectors":
        from aid_connector_worker.handlers import router as schedule

        return [schedule]
    if worker == "correlation":
        from aid_correlation_worker.handlers import router as close

        return [close]
    if worker == "diagnosis":
        from aid_diagnosis_worker.handlers import router as knowledge

        return [knowledge]
    if worker == "notifier":
        from aid_notifier.handlers import router as alerts

        return [alerts]
    return []


async def process(worker: str, topic: str, message: PubSubMessage, handler: Handler) -> bool:
    """Roda o handler no contexto da mensagem (tópico, tenant e trace). `False`: falhou e deve
    ser reentregue (no push, o 500; no RabbitMQ, a fila de espera)."""
    attributes = message.attributes
    # Filho do span de quem gravou a mensagem na outbox (atributo `traceparent`, #34).
    with (
        tracer.start_as_current_span(
            f"pubsub {topic}", context=context_from(attributes), kind=SpanKind.CONSUMER
        ) as span,
        bind(
            worker=worker,
            topic=topic,
            message_id=message.message_id,
            tenant_id=attributes.get("tenant_id"),
        ),
    ):
        span.set_attribute("messaging.message.id", message.message_id)
        if attributes.get("tenant_id"):
            span.set_attribute("tenant.id", attributes["tenant_id"])
        try:
            await handler(message)
        except Exception as exc:
            # Registrado aqui, dentro do contexto (tópico, mensagem, tenant e trace).
            logger.exception("falha ao processar a mensagem")
            span.record_exception(exc)
            return False
        finally:
            tracing.flush()
    return True


def create_app(
    worker: str, handlers: Mapping[str, Handler], amqp_url: str | None = None
) -> FastAPI:
    """Com `amqp_url` (Railway, ADR-0024), o worker também consome as filas do RabbitMQ dos seus
    tópicos; sem ele, recebe só o push do Pub/Sub em `/pubsub` (GCP)."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        consumer = None
        if amqp_url and handlers:
            from aid_worker.rabbit import Consumer

            consumer = Consumer(amqp_url, worker, handlers)
            await consumer.start()
        try:
            yield
        finally:
            if consumer is not None:
                await consumer.close()

    app = FastAPI(title=f"worker-{worker}", openapi_url=None, lifespan=lifespan)

    # Healthcheck do deploy no Railway: o app só sobe depois de conectar ao broker.
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/pubsub", status_code=status.HTTP_204_NO_CONTENT)
    async def receive(envelope: PushEnvelope) -> Response:
        topic = topic_of(envelope.subscription)
        handler = handlers.get(topic)
        if handler is None:
            # Só identificadores: o conteúdo da mensagem pode trazer dados de clientes.
            logger.warning(
                "sem handler: worker=%s topic=%s message_id=%s",
                worker,
                topic,
                envelope.message.message_id,
            )
            return Response(status_code=status.HTTP_501_NOT_IMPLEMENTED)
        if not await process(worker, topic, envelope.message, handler):
            # O 500 faz o Pub/Sub reentregar.
            return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    for router in routers_for(worker):
        app.include_router(router)
    return app


WORKER = os.environ.get("WORKER_NAME", "")
# Logs JSON para o Cloud Logging e traces no Cloud Trace (com OTEL_ENABLED), antes das rotas.
logs.configure_logging()
tracing.configure(f"worker-{WORKER}")
app = create_app(WORKER, handlers_for(WORKER), os.environ.get("AMQP_URL"))
