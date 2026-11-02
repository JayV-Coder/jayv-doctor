"""Detectores de segredos e dados pessoais. A ordem importa: segredos antes de PII, e padrões mais
específicos antes dos genéricos (cartão antes de telefone, CNPJ antes de CPF)."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from ipaddress import ip_address


@dataclass(frozen=True)
class Detector:
    kind: str
    pattern: re.Pattern[str]
    # Confere o trecho achado (dígito verificador, Luhn); `None` aceita tudo.
    check: Callable[[str], bool] | None = None
    # Grupo que vira marcador; 0 é o trecho inteiro. Em `password=valor`, só o valor.
    group: int = 0


def digits(text: str) -> list[int]:
    return [int(char) for char in text if char.isdigit()]


def luhn(text: str) -> bool:
    numbers = digits(text)[::-1]
    total = sum(
        number if index % 2 == 0 else (number * 2 - 9 if number > 4 else number * 2)
        for index, number in enumerate(numbers)
    )
    return 13 <= len(numbers) <= 19 and total % 10 == 0


def cpf(text: str) -> bool:
    numbers = digits(text)
    if len(numbers) != 11 or len(set(numbers)) == 1:
        return False
    for size in (9, 10):
        total = sum(n * w for n, w in zip(numbers[:size], range(size + 1, 1, -1), strict=True))
        if (total * 10 % 11) % 10 != numbers[size]:
            return False
    return True


def cnpj(text: str) -> bool:
    numbers = digits(text)
    if len(numbers) != 14 or len(set(numbers)) == 1:
        return False
    weights = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for size in (12, 13):
        total = sum(n * w for n, w in zip(numbers[:size], weights[-size:], strict=True))
        expected = 0 if total % 11 < 2 else 11 - total % 11
        if expected != numbers[size]:
            return False
    return True


def public_ip(text: str) -> bool:
    try:
        address = ip_address(text)
    except ValueError:
        return False
    return not (address.is_private or address.is_loopback or address.is_link_local)


def valid_ip(text: str) -> bool:
    try:
        ip_address(text)
    except ValueError:
        return False
    return True


SECRETS = [
    Detector(
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    ),
    # Token real tem 16+ caracteres: "Bearer token missing" não é segredo.
    Detector("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{16,}=*")),
    Detector("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")),
    Detector("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    Detector("gcp_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}(?![0-9A-Za-z_\-])")),
    Detector("gcp_token", re.compile(r"\bya29\.[0-9A-Za-z_\-]{20,}")),
    Detector("salesforce_session", re.compile(r"\b00D[0-9A-Za-z]{12,15}![0-9A-Za-z._]{20,}")),
    Detector(
        "password",
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|senha|secret|client_secret|api_key|apikey)[\"']?"
            r"\s*[=:]\s*(\"[^\"]*\"|'[^']*'|[^\s&;,\"']+)"
        ),
        group=1,
    ),
    Detector("authorization", re.compile(r"(?im)\bauthorization\s*:\s*([^\r\n]+)"), group=1),
    Detector("cookie", re.compile(r"(?im)\b(?:set-)?cookie\s*:\s*([^\r\n]+)"), group=1),
]

PERSONAL = [
    Detector("cartao", re.compile(r"\b\d(?:[ -]?\d){12,18}\b"), luhn),
    Detector("cnpj", re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"), cnpj),
    Detector("cpf", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), cpf),
    Detector("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # Exige formato de telefone (+55, DDD entre parênteses ou separadores): um número de pedido
    # de 10 ou 11 dígitos colados não vira telefone.
    Detector(
        "telefone",
        re.compile(
            r"\+55\s?\(?\d{2}\)?\s?9?\d{4}[\s-]?\d{4}\b"
            r"|(?:\(\d{2}\)\s?|(?<![\d.])\b\d{2}[\s-])(?:9\d{4}|\d{4})[\s-]\d{4}\b"
        ),
    ),
]

IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
