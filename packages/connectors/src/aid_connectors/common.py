"""Peças comuns aos Conectores: a categoria do erro pelo status HTTP e a troca de endpoint que
só o E2E usa (aceita só loopback, nunca um host de verdade)."""

from urllib.parse import urlparse

STATUS_CATEGORIES = {
    401: "AUTH",
    403: "AUTH",
    408: "TIMEOUT",
    504: "TIMEOUT",
    429: "RATE_LIMIT",
    409: "DUPLICATE",
    400: "VALIDATION",
    422: "VALIDATION",
    502: "CONNECTIVITY",
    503: "CONNECTIVITY",
}


def is_loopback(url: str) -> bool:
    """`http://127.0.0.1:<porta>` ou `http://localhost:<porta>`, sem usuário na URL: um prefixo
    como `http://127.0.0.1:1@evil.com` aponta para outro host e é recusado."""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname in ("127.0.0.1", "localhost")
        and port is not None
        and parsed.username is None
        and parsed.password is None
    )
