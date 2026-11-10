"""Entrega por canal. Cada envio recebe só a `Message` (título, corpo curto e link) e o destino;
nenhum canal vê log, Evidência ou dado de negócio."""

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx
from aid_alerts import Message, push_endpoint_allowed, webhook_allowed
from aid_alerts.mail import Mailer, mailer_from_env

log = logging.getLogger(__name__)


class DeliveryError(Exception):
    """Falha classificada da entrega; a mensagem vai para o histórico, sem o endereço."""


@dataclass(frozen=True)
class PushTarget:
    id: str
    endpoint: str
    p256dh: str
    auth: str


# Resultado de um push: True entregue; False assinatura que não vale mais (apagar).
PushSender = Callable[[PushTarget, Message], Awaitable[bool]]
WebhookSender = Callable[[str, str, Message], Awaitable[None]]


def slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def post_webhook(kind: str, url: str, message: Message) -> None:
    if not webhook_allowed(kind, url):
        raise DeliveryError(f"endereço do {kind} fora dos hosts permitidos")
    # O nome da Integração vem do cliente: sem o escape, `<!channel>` ou `<url|texto>` viraria
    # menção ou link disfarçado no Slack.
    text = (
        f"*{slack_escape(message.title)}*\n{slack_escape(message.body)}\n"
        f"<{message.url}|{slack_escape(message.action)}>"
    )
    if kind == "slack":
        body: dict[str, Any] = {"text": text}
    else:
        # Teams (Incoming Webhook ou Workflows): Adaptive Card com o link.
        body = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "body": [
                            {"type": "TextBlock", "text": message.title, "weight": "Bolder"},
                            {"type": "TextBlock", "text": message.body, "wrap": True},
                        ],
                        "actions": [
                            {"type": "Action.OpenUrl", "title": message.action, "url": message.url}
                        ],
                    },
                }
            ],
        }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0), follow_redirects=False) as client:
            response = await client.post(url, json=body)
    except httpx.HTTPError as exc:
        raise DeliveryError(f"o {kind} não respondeu") from exc
    if response.status_code >= 300:
        raise DeliveryError(f"o {kind} respondeu HTTP {response.status_code}")


@lru_cache(maxsize=1)
def vapid_key(raw: str) -> Any:
    """A chave privada VAPID do segredo, em PEM (como a doc gera) ou DER em base64. A biblioteca
    só lê PEM pelo objeto `Vapid02`, não como texto."""
    from py_vapid import Vapid02  # type: ignore[import-untyped]

    text = raw.strip()
    if text.startswith("-----BEGIN"):
        return Vapid02.from_pem(text.encode())
    return Vapid02.from_string(private_key=text)


async def send_push(target: PushTarget, message: Message) -> bool:
    """Web Push com VAPID (`AID_VAPID_PRIVATE_KEY`, `AID_VAPID_SUBJECT`). Endpoint fora dos
    serviços de push dos navegadores não recebe nada (conferido também na API)."""
    if not push_endpoint_allowed(target.endpoint):
        return False
    from pywebpush import (  # type: ignore[import-untyped]
        WebPushException,
        webpush,
    )

    payload = json.dumps(
        {"title": message.title, "body": message.body, "url": message.url}, ensure_ascii=False
    )
    claims: dict[str, str | int] = {
        "sub": os.environ.get("AID_VAPID_SUBJECT", "mailto:alertas@jayv.dev")
    }

    raw_key = os.environ.get("AID_VAPID_PRIVATE_KEY")
    if not raw_key:
        raise DeliveryError("push sem a chave VAPID configurada")
    try:
        key = vapid_key(raw_key)
    except Exception as exc:
        raise DeliveryError("chave VAPID inválida") from exc

    def deliver() -> bool:
        try:
            webpush(
                {
                    "endpoint": target.endpoint,
                    "keys": {"p256dh": target.p256dh, "auth": target.auth},
                },
                data=payload,
                vapid_private_key=key,
                vapid_claims=claims,
                ttl=3600,
                timeout=10,
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                return False
            raise DeliveryError(f"o serviço de push respondeu HTTP {status}") from exc
        except Exception as exc:
            # Rede (timeout, conexão) e o resto da biblioteca: falha classificada, sem detalhe.
            raise DeliveryError("o serviço de push não respondeu") from exc
        return True

    return await asyncio.to_thread(deliver)


@dataclass
class Senders:
    """Os envios de verdade; os testes trocam por fakes."""

    webhook: WebhookSender = post_webhook
    push: PushSender = send_push
    mailer: Callable[[], Mailer] = mailer_from_env

    async def email(self, to: Sequence[str], message: Message) -> None:
        """Um e-mail por destinatário: ninguém vê o endereço dos colegas."""
        body = f"{message.body}\n\n{message.action}: {message.url}\n"
        mailer = self.mailer()
        failed = 0
        for address in to:
            try:
                await asyncio.to_thread(mailer.send, [address], message.title, body)
            except Exception:
                failed += 1
        if failed == len(to):
            raise DeliveryError("o servidor de e-mail recusou o envio")
