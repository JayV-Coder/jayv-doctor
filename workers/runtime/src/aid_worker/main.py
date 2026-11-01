"""Recebe o push autenticado do Pub/Sub e entrega ao handler do worker.

Qualquer resposta fora de 2xx faz o Pub/Sub reentregar a mensagem e, depois de 5 tentativas,
movê-la para a DLQ. Por isso worker sem handler responde 501 em vez de confirmar: confirmar
descartaria a mensagem. A validação do OIDC é do Cloud Run, com o `run.invoker` do Terraform.
"""

import logging
import os
from collections.abc import Awaitable, Callable, Mapping

from fastapi import FastAPI, Response, status
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

# Chave: nome do tópico. Um worker pode receber mais de um, com formatos diferentes.
HANDLERS: dict[str, Handler] = {}


def topic_of(subscription: str) -> str:
    """`projects/x/subscriptions/ingestion.raw.push` => `ingestion.raw` (ver Terraform)."""
    return subscription.rsplit("/", 1)[-1].removesuffix(".push")


def create_app(worker: str, handlers: Mapping[str, Handler]) -> FastAPI:
    app = FastAPI(title=f"worker-{worker}", openapi_url=None)

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
        await handler(envelope.message)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_app(os.environ.get("WORKER_NAME", ""), HANDLERS)
