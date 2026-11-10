"""Atualização assinada: a plataforma anuncia versão, URL, sha256 e a assinatura Ed25519 da chave
de release. O agente só aplica com a assinatura válida (chave pública em `AID_AGENT_RELEASE_KEY`,
fixada na imagem) e o sha256 batendo; aplicar é trocar o pacote de forma atômica e sair para o
supervisor (Docker, systemd) reiniciar com a versão nova."""

import base64
import hashlib
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

RESTART = 75


def signed_payload(manifest: Mapping[str, Any]) -> bytes:
    return f"{manifest['version']}\n{manifest['sha256']}\n{manifest['url']}".encode()


def verify_manifest(manifest: Mapping[str, Any], release_key: str | None) -> bool:
    if not release_key:
        return False
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(release_key, validate=True))
        key.verify(
            base64.b64decode(str(manifest["signature"]), validate=True), signed_payload(manifest)
        )
    except (ValueError, KeyError, InvalidSignature):
        return False
    return True


def apply(
    manifest: Mapping[str, Any],
    target: Path,
    fetch: Callable[[str], bytes],
    release_key: str | None = None,
) -> bool:
    """True quando a versão nova está no lugar e o agente deve reiniciar."""
    key = release_key if release_key is not None else os.environ.get("AID_AGENT_RELEASE_KEY")
    if not verify_manifest(manifest, key) or not str(manifest["url"]).startswith("https://"):
        return False
    data = fetch(str(manifest["url"]))
    if hashlib.sha256(data).hexdigest() != manifest["sha256"]:
        return False
    staging = target.with_suffix(target.suffix + ".new")
    staging.write_bytes(data)
    os.chmod(staging, 0o700)  # só o usuário do agente executa
    os.replace(staging, target)
    return True
