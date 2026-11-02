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
    # Grupo que vira marcador; 0 é o trecho inteiro. Em `password=valor`, só o valor; -1 é o
    # primeiro grupo que participou (padrão com formas alternativas de valor).
    group: int = 0
    # Trechos literais, em minúsculas, sem os quais o padrão não casa: sem nenhum deles no texto,
    # o detector nem roda. É o que mantém a meta de 10 mil registros por segundo.
    hints: tuple[str, ...] = ()
    # Só casa com dígitos no texto (cartão, documentos, telefone, IP).
    needs_digit: bool = False


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


# Nome de credencial, com qualquer prefixo (`DB_PASSWORD`, `smtp_password`, `x-api-key`): sem
# `\b` na frente, o prefixo não importa.
CREDENTIAL_NAMES = ("password", "passwd", "pwd", "senha", "secret", "apikey", "api_key", "api-key")
SESSION_NAMES = ("token",)
# Entre o nome e o valor: aspas (inclusive escapadas, de JSON dentro de string) e `=` ou `:`.
GLUE = r"[\\\"']*\s*[=:]\s*"
# Valor entre aspas sai inteiro; sem aspas, até o próximo separador.
VALUE = r"(?:\\?\"((?:[^\"\\]|\\[^\"])*)\\?\"|'([^']*)'|([^\s&;,\\\"']+))"
HEADER_VALUE = r"[\\\"']*\s*:\s*[\\\"']*([^\r\n\\\"']+)"


def credential(kind: str, names: tuple[str, ...]) -> Detector:
    key = "|".join(re.escape(name) for name in names)
    return Detector(kind, re.compile(rf"(?i)(?:{key}){GLUE}{VALUE}"), group=-1, hints=names)


SECRETS = [
    # Sem a linha END (cortada pelo limite de tamanho, ou log linha a linha), vai até o fim.
    Detector(
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.*?-----END [A-Z ]*PRIVATE KEY-----|.*)", re.S
        ),
        hints=("private key",),
    ),
    # Token real tem 16+ caracteres: "Bearer token missing" não é segredo.
    Detector("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{16,}=*"), hints=("bearer",)),
    Detector(
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*"),
        hints=("eyj",),
    ),
    Detector("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), hints=("akia", "asia")),
    Detector("gcp_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}(?![0-9A-Za-z_\-])"), hints=("aiza",)),
    Detector("gcp_token", re.compile(r"\bya29\.[0-9A-Za-z_\-]{20,}"), hints=("ya29.",)),
    Detector(
        "salesforce_session",
        re.compile(r"\b00D[0-9A-Za-z]{12,15}![0-9A-Za-z._]{20,}"),
        hints=("00d",),
    ),
    Detector(
        "authorization",
        re.compile(rf"(?im)\b(?:proxy-)?authorization{HEADER_VALUE}"),
        group=1,
        hints=("authorization",),
    ),
    Detector(
        "cookie", re.compile(rf"(?im)\b(?:set-)?cookie{HEADER_VALUE}"), group=1, hints=("cookie",)
    ),
    credential("password", CREDENTIAL_NAMES),
    credential("token", SESSION_NAMES),
]

PERSONAL = [
    # Grupos de 4 (ou 4-6-5 da Amex) antes dos dígitos corridos: com a validade ou o CVV logo
    # depois, o número inteiro ainda é achado.
    Detector(
        "cartao",
        re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b|\b\d{4}[ -]\d{6}[ -]\d{5}\b|\b\d{13,19}\b"),
        luhn,
        needs_digit=True,
    ),
    Detector(
        "cnpj", re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"), cnpj, needs_digit=True
    ),
    Detector("cpf", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), cpf, needs_digit=True),
    Detector(
        "email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), hints=("@",)
    ),
    # Exige formato de telefone (+55, DDD entre parênteses ou separadores): um número de pedido
    # de 10 ou 11 dígitos colados não vira telefone.
    Detector(
        "telefone",
        re.compile(
            r"\+55\s?\(?\d{2}\)?\s?9?\d{4}[\s-]?\d{4}\b"
            r"|(?:\(\d{2}\)\s?|(?<![\d.])\b\d{2}[\s-])(?:9\d{4}|\d{4})[\s-]\d{4}\b"
        ),
        needs_digit=True,
    ),
]

IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
