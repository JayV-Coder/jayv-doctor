"""Referência de negócio: identificador comercial guardado como HMAC por tenant.

A chave do tenant é derivada por HKDF da chave mestre (Secret Manager) com o `tenant_id`, então o
mesmo pedido gera valores diferentes em cada Organização e a busca exata continua possível: a API
aplica o mesmo HMAC ao termo digitado.
"""

import hashlib
import hmac
from uuid import UUID

PREFIX = "hmac:"
INFO = b"aid:business-reference:v1"


def hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """HKDF do RFC 5869 com SHA-256."""
    prk = hmac.new(salt or bytes(32), ikm, hashlib.sha256).digest()
    output, block = b"", b""
    counter = 1
    while len(output) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        output += block
        counter += 1
    return output[:length]


def derive_tenant_key(master_key: bytes, tenant_id: UUID) -> bytes:
    return hkdf_sha256(master_key, salt=tenant_id.bytes, info=INFO, length=32)


def reference_hmac(tenant_key: bytes, value: str) -> str:
    """`hmac:` + 16 hex (64 bits): curto para índice e sem colisão prática dentro do tenant."""
    digest = hmac.new(tenant_key, value.strip().encode(), hashlib.sha256).hexdigest()
    return f"{PREFIX}{digest[:16]}"
