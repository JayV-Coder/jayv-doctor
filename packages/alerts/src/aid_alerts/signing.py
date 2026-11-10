"""Assinatura dos webhooks (#42): `X-AID-Signature: t=<segundos Unix>,v1=<hex>`, com
`v1 = HMAC-SHA256(segredo, f"{t}.{corpo}")`. Quem recebe confere o HMAC com o corpo exato que
chegou e recusa `t` fora de 5 min (anti-replay). `verify` é a referência dos exemplos em
docs/api/webhooks.md."""

import hashlib
import hmac
import secrets
import time

PREFIX = "whsec_"
TOLERANCE_SECONDS = 300


def new_secret() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def signature(secret: str, body: bytes, timestamp: int) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"t={timestamp},v1={mac.hexdigest()}"


def sign(secret: str, body: bytes, now: float | None = None) -> str:
    return signature(secret, body, int(now if now is not None else time.time()))


def verify(secret: str, header: str, body: bytes, now: float | None = None) -> bool:
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    try:
        timestamp = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs((now if now is not None else time.time()) - timestamp) > TOLERANCE_SECONDS:
        return False
    expected = signature(secret, body, timestamp).split("v1=", 1)[1]
    return hmac.compare_digest(expected, parts.get("v1", ""))
