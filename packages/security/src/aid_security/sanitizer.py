"""`Sanitizer.sanitize(record) -> (record, report)`: remove segredos e dados pessoais antes de o
registro virar Evento ou ir para o LLM (PRD §8). Nunca lança exceção por causa do conteúdo."""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from aid_security.detectors import IPV4, PERSONAL, SECRETS, Detector, public_ip, valid_ip
from aid_security.references import reference_hmac

MAX_STRING_BYTES = 8192
MAX_DEPTH = 10
TRUNCATED = "[TRUNCADO]"
TOO_DEEP = "[TRUNCADO:profundidade]"

# Campos removidos inteiros pelo nome, em qualquer nível: o valor nem é inspecionado.
SENSITIVE_KEYS = {
    "authorization": "authorization",
    "proxy-authorization": "authorization",
    "cookie": "cookie",
    "set-cookie": "cookie",
    "password": "password",
    "passwd": "password",
    "senha": "password",
    "secret": "password",
    "client_secret": "password",
    "api_key": "password",
    "apikey": "password",
    "x-api-key": "password",
    "access_token": "token",
    "refresh_token": "token",
    "id_token": "token",
    "token": "token",
    "private_key": "private_key",
}


def marker(kind: str) -> str:
    return f"[REMOVIDO:{kind}]"


@dataclass(frozen=True)
class Rules:
    """Regras do tenant: padrões extras e o tratamento de IPs."""

    extra_patterns: Mapping[str, str] = field(default_factory=dict)
    detect_ips: bool = True
    allow_private_ips: bool = False


@dataclass
class Report:
    counts: Counter[str] = field(default_factory=Counter)
    truncated: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"counts": dict(self.counts), "truncated": self.truncated}


class Sanitizer:
    def __init__(
        self,
        rules: Rules | None = None,
        reference_fields: Iterable[str] = (),
        reference_key: bytes | None = None,
    ) -> None:
        self.rules = rules or Rules()
        self.reference_fields = frozenset(name.lower() for name in reference_fields)
        if self.reference_fields and reference_key is None:
            raise ValueError("campos de Referência exigem a chave do tenant")
        self.reference_key = reference_key
        extras = [
            Detector(kind, re.compile(pattern))
            for kind, pattern in self.rules.extra_patterns.items()
        ]
        ips = []
        if self.rules.detect_ips:
            ips.append(
                Detector("ip", IPV4, public_ip if self.rules.allow_private_ips else valid_ip)
            )
        # A ordem é a prioridade: em trechos sobrepostos vale o primeiro detector.
        self.detectors: tuple[Detector, ...] = (*SECRETS, *extras, *PERSONAL, *ips)
        self.sensitive_keys = MappingProxyType(SENSITIVE_KEYS)

    def sanitize(self, record: Any) -> tuple[Any, Report]:
        report = Report()
        return self._value(record, report, depth=0), report

    def _value(self, value: Any, report: Report, depth: int) -> Any:
        if isinstance(value, Mapping):
            if depth >= MAX_DEPTH:
                report.truncated += 1
                return TOO_DEEP
            return {key: self._field(key, item, report, depth) for key, item in value.items()}
        if isinstance(value, list | tuple):
            if depth >= MAX_DEPTH:
                report.truncated += 1
                return TOO_DEEP
            return [self._value(item, report, depth + 1) for item in value]
        if isinstance(value, str):
            return self._text(value, report)
        if isinstance(value, int | float) and not isinstance(value, bool):
            # Número pode ser CPF, CNPJ ou cartão: só vira texto se algo for removido.
            text = str(value)
            cleaned = self._text(text, report)
            return value if cleaned == text else cleaned
        return value

    def _field(self, key: Any, value: Any, report: Report, depth: int) -> Any:
        name = str(key).lower()
        if name in self.reference_fields and isinstance(value, str | int) and self.reference_key:
            report.counts["referencia"] += 1
            return reference_hmac(self.reference_key, str(value))
        kind = self.sensitive_keys.get(name)
        if kind is not None and value not in (None, ""):
            report.counts[kind] += 1
            return marker(kind)
        return self._value(value, report, depth + 1)

    def _text(self, text: str, report: Report) -> str:
        encoded = text.encode()
        truncated = len(encoded) > MAX_STRING_BYTES
        if truncated:
            report.truncated += 1
            text = encoded[:MAX_STRING_BYTES].decode(errors="ignore")
        text = self._replace(text, self._spans(text), report)
        return f"{text}{TRUNCATED}" if truncated else text

    def _spans(self, text: str) -> list[tuple[int, int, str]]:
        """Trechos a remover, todos achados no texto original: um marcador inserido não cria
        fronteira de palavra nova para o detector seguinte, e sanitizar de novo não muda nada."""
        spans: list[tuple[int, int, str]] = []
        for detector in self.detectors:
            for match in detector.pattern.finditer(text):
                found = match.group(detector.group)
                start, end = match.span(detector.group)
                if found.startswith("[REMOVIDO:"):
                    continue
                if detector.check is not None and not detector.check(found):
                    continue
                if any(
                    start < taken_end and taken_start < end for taken_start, taken_end, _ in spans
                ):
                    continue
                spans.append((start, end, detector.kind))
        return sorted(spans)

    @staticmethod
    def _replace(text: str, spans: list[tuple[int, int, str]], report: Report) -> str:
        parts, position = [], 0
        for start, end, kind in spans:
            parts.append(text[position:start])
            parts.append(marker(kind))
            report.counts[kind] += 1
            position = end
        parts.append(text[position:])
        return "".join(parts)
