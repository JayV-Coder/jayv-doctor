"""Identidade do agente: a chave Ed25519 gerada aqui (nunca sai da máquina), o segredo e o id
devolvidos no registro, e a assinatura de cada requisição. Tudo em arquivos 0600 na pasta de
estado (`AID_AGENT_STATE`, padrão /var/lib/aid-agent)."""

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KEY_FILE = "agent.key"
STATE_FILE = "agent.json"
CERT_FILE = "agent.crt"


def write_private(path: Path, content: bytes) -> None:
    """Grava com 0600 desde a criação (sem janela com permissão aberta)."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write(content)


def load_or_create_key(state: Path) -> Ed25519PrivateKey:
    path = state / KEY_FILE
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError(f"{path} não é uma chave Ed25519")
        return key
    key = Ed25519PrivateKey.generate()
    write_private(
        path,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    return key


def public_key(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


@dataclass(frozen=True)
class Credentials:
    api_url: str
    agent_id: str
    secret: str


def save_credentials(state: Path, credentials: Credentials, certificate: str | None) -> None:
    write_private(state / STATE_FILE, json.dumps(credentials.__dict__).encode())
    if certificate:
        write_private(state / CERT_FILE, certificate.encode())


def load_credentials(state: Path) -> Credentials | None:
    path = state / STATE_FILE
    if not path.exists():
        return None
    return Credentials(**json.loads(path.read_text()))


def signature_headers(
    key: Ed25519PrivateKey,
    secret: str,
    method: str,
    path: str,
    body: bytes,
    now: float | None = None,
) -> dict[str, str]:
    """Os cabeçalhos que a API confere: segredo, instante e a assinatura de método, caminho,
    instante e sha256 do corpo."""
    timestamp = str(int(now if now is not None else time.time()))
    message = f"{method.upper()}\n{path}\n{timestamp}\n{hashlib.sha256(body).hexdigest()}".encode()
    return {
        "authorization": f"Bearer {secret}",
        "x-aid-timestamp": timestamp,
        "x-aid-signature": base64.b64encode(key.sign(message)).decode(),
    }
