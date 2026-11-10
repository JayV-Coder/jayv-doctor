"""Envio de verdade do Web Push (#41): chave VAPID em PEM, payload criptografado (aes128gcm) e
assinatura VAPID, contra um serviço de push local."""

import asyncio
import base64
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from aid_alerts import Message
from aid_notifier import channels
from aid_notifier.channels import PushTarget, send_push
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

received: dict[str, Any] = {}


class Service(BaseHTTPRequestHandler):
    status = 201

    def do_POST(self) -> None:
        received["encoding"] = self.headers.get("Content-Encoding")
        received["authorization"] = self.headers.get("Authorization", "")
        received["size"] = len(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(Service.status)
        self.end_headers()

    def log_message(self, *_: Any) -> None:
        return None


@pytest.fixture
def service() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), Service)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/push"
    server.shutdown()


def device(endpoint: str) -> PushTarget:
    key = ec.generate_private_key(ec.SECP256R1())
    raw = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    p256dh = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    auth = base64.urlsafe_b64encode(b"0123456789abcdef").decode().rstrip("=")
    return PushTarget("s-1", endpoint, p256dh, auth)


def test_push_com_chave_pem_criptografa_e_assina(
    service: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from py_vapid import Vapid02  # type: ignore[import-untyped]

    vapid = Vapid02()
    vapid.generate_keys()
    monkeypatch.setenv("AID_VAPID_PRIVATE_KEY", vapid.private_pem().decode())
    # O serviço local não está na allowlist dos navegadores: só aqui ela é afrouxada.
    monkeypatch.setattr(channels, "push_endpoint_allowed", lambda _: True)
    message = Message("Incidente crítico #1", "Timeout · Pedidos · prd", "https://app/incidentes/x")
    Service.status = 201
    assert asyncio.run(send_push(device(service), message)) is True
    assert received["encoding"] == "aes128gcm"
    assert received["authorization"].startswith("vapid t=")
    assert received["size"] > len(json.dumps({"title": message.title}))
    # Assinatura que não existe mais: o serviço responde 410 e o `notifier` a apaga.
    Service.status = 410
    assert asyncio.run(send_push(device(service), message)) is False


def test_endpoint_fora_dos_navegadores_nem_e_chamado(service: str) -> None:
    received.clear()
    message = Message("t", "b", "u")
    assert asyncio.run(send_push(device(service), message)) is False
    assert received == {}


def test_texto_do_slack_escapa_o_que_vem_do_cliente() -> None:
    from aid_notifier.channels import slack_escape

    assert slack_escape("Pedidos <!channel> & <https://evil.test|Clique>") == (
        "Pedidos &lt;!channel&gt; &amp; &lt;https://evil.test|Clique&gt;"
    )
