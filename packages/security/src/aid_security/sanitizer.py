"""`Sanitizer.sanitize(record) -> (record, report)`: remove segredos e dados pessoais antes de o
registro virar Evento ou ir para o LLM (PRD §8). Nunca lança exceção por causa do conteúdo."""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from aid_security.detectors import IPV4, PERSONAL, SECRETS, Detector, public_ip, valid_ip
from aid_security.references import reference_hmac

MAX_STRING_BYTES = 8192
MAX_DEPTH = 10
TRUNCATED = "[TRUNCADO]"
TOO_DEEP = "[TRUNCADO:profundidade]"

MAX_EXTRA_PATTERN = 200
# Quantificador sobre grupo que já tem quantificador, como `(a+)+`: backtracking catastrófico.
NESTED_QUANTIFIER = re.compile(r"\([^)]*[+*}][^)]*\)\s*[+*{]")

# Campos removidos inteiros pelo nome, em qualquer nível e grafia (`accessToken`, `DB_PASSWORD`,
# `x-api-key`): o valor nem é inspecionado. Comparado depois de tirar `_`, `-` e espaço.
KEY_SUFFIXES = (
    ("authorization", "authorization"),
    ("cookie", "cookie"),
    ("privatekey", "private_key"),
    ("token", "token"),
    ("password", "password"),
    ("passwd", "password"),
    ("senha", "password"),
    ("secret", "password"),
    ("apikey", "password"),
)
EXACT_KEYS = {"pwd": "password"}


def sensitive_kind(key: str) -> str | None:
    name = re.sub(r"[\s_-]", "", key).lower()
    if name in EXACT_KEYS:
        return EXACT_KEYS[name]
    return next((kind for suffix, kind in KEY_SUFFIXES if name.endswith(suffix)), None)


def compile_extra(kind: str, pattern: str) -> re.Pattern[str]:
    """Padrão do tenant, conferido na configuração: inválido, vazio ou catastrófico é recusado."""
    if len(pattern) > MAX_EXTRA_PATTERN or NESTED_QUANTIFIER.search(pattern):
        raise ValueError(f"padrão de {kind} longo demais ou com quantificador aninhado")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"padrão de {kind} inválido: {exc}") from exc
    if compiled.search("") is not None:
        raise ValueError(f"padrão de {kind} casa com texto vazio")
    return compiled


DIGIT = re.compile(r"\d")
# Chave que é só um identificador (`order_id`, `httpStatus`) não tem como conter PII nem segredo.
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")


def first_group(match: re.Match[str]) -> int:
    return next(index for index, value in enumerate(match.groups(), 1) if value is not None)


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
        if self.reference_fields and (reference_key is None or len(reference_key) < 16):
            raise ValueError("campos de Referência exigem a chave do tenant (16+ bytes)")
        self.reference_key = reference_key or b""
        extras = [
            Detector(kind, compile_extra(kind, pattern))
            for kind, pattern in self.rules.extra_patterns.items()
        ]
        ips = []
        if self.rules.detect_ips:
            check = public_ip if self.rules.allow_private_ips else valid_ip
            ips.append(Detector("ip", IPV4, check, hints=(".",), needs_digit=True))
        # A ordem é a prioridade: em trechos sobrepostos vale o primeiro detector.
        self.detectors: tuple[Detector, ...] = (*SECRETS, *extras, *PERSONAL, *ips)
        # Uma varredura só acha as pistas presentes no texto (o lookahead pega as sobrepostas);
        # detector sem pista presente não roda.
        hints = sorted({hint for detector in self.detectors for hint in detector.hints})
        self.hint_pattern = re.compile(f"(?=({'|'.join(re.escape(hint) for hint in hints)}))")

    def sanitize(self, record: Any) -> tuple[Any, Report]:
        report = Report()
        return self._value(record, report, depth=0), report

    def _value(self, value: Any, report: Report, depth: int) -> Any:
        if isinstance(value, Mapping):
            if depth >= MAX_DEPTH:
                report.truncated += 1
                return TOO_DEEP
            result: dict[Any, Any] = {}
            for key, item in value.items():
                # A chave também pode ser PII (mapa por e-mail ou CPF); colisão não apaga valor.
                name = (
                    self._text(key, report)
                    if isinstance(key, str) and not IDENTIFIER.match(key)
                    else key
                )
                unique, suffix = name, 2
                while unique in result:
                    unique, suffix = f"{name}#{suffix}", suffix + 1
                result[unique] = self._field(key, item, report, depth)
            return result
        if isinstance(value, list | tuple):
            if depth >= MAX_DEPTH:
                report.truncated += 1
                return TOO_DEEP
            return [self._value(item, report, depth + 1) for item in value]
        if isinstance(value, str):
            return self._text(value, report)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return self._number(value, report)
        return value

    def _number(self, value: float, report: Report) -> Any:
        """Número pode ser CPF, CNPJ ou cartão: só vira texto se algo for removido. Inteiro perde
        os zeros à esquerda, então CPF e CNPJ também são conferidos com eles de volta."""
        text = str(value)
        candidates = [text]
        if isinstance(value, int) and value > 0:
            if 9 <= len(text) < 11:
                candidates.append(text.zfill(11))
            if 12 <= len(text) < 14:
                candidates.append(text.zfill(14))
        for candidate in candidates:
            cleaned = self._text(candidate, report)
            if cleaned != candidate:
                return cleaned
        return value

    def _field(self, key: Any, value: Any, report: Report, depth: int) -> Any:
        name = str(key).lower()
        if name in self.reference_fields and value is not None and not isinstance(value, bool):
            report.counts["referencia"] += 1
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            if isinstance(value, str | int | float):
                return reference_hmac(self.reference_key, str(value))
            # Referência não é objeto nem lista: na dúvida, não sai em claro.
            return marker("referencia")
        kind = sensitive_kind(str(key))
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
        present = set(self.hint_pattern.findall(text.lower()))
        has_digit = DIGIT.search(text) is not None
        for detector in self.detectors:
            if detector.needs_digit and not has_digit:
                continue
            if detector.hints and present.isdisjoint(detector.hints):
                continue
            for match in detector.pattern.finditer(text):
                group = detector.group if detector.group >= 0 else first_group(match)
                found = match.group(group)
                start, end = match.span(group)
                if start == end or found.startswith("[REMOVIDO:"):
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
