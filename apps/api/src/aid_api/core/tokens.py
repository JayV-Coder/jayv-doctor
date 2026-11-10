"""Tokens de uso externo (links, registros, endereços de webhook): o banco guarda só o hash."""

import hashlib


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
