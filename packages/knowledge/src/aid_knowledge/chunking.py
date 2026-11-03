"""Fragmentos pela estrutura do texto: títulos e parágrafos, de 500 a 800 tokens, com 80 de
sobreposição entre um e o seguinte (a frase cortada no fim aparece inteira no próximo)."""

import math
import re
from dataclasses import dataclass

MIN_TOKENS = 500
MAX_TOKENS = 800
OVERLAP_TOKENS = 80
# Pedaços pequenos o bastante para o pacote sempre fechar acima do mínimo.
UNIT_TOKENS = 300
CHARS_PER_TOKEN = 3.5
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    content: str
    tokens: int
    heading: str | None


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _split_words(text: str, limit: int) -> list[str]:
    pieces: list[str] = []
    current: list[str] = []
    for word in text.split():
        if current and estimate_tokens(" ".join([*current, word])) > limit:
            pieces.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        pieces.append(" ".join(current))
    return pieces


def _units(text: str) -> list[tuple[str, str | None]]:
    """(texto, título em vigor) por parágrafo, quebrando os grandes em pedaços."""
    heading: str | None = None
    units: list[tuple[str, str | None]] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        first = block.splitlines()[0]
        if (found := HEADING.match(first)) is not None:
            heading = found.group(1)
        if estimate_tokens(block) <= UNIT_TOKENS:
            units.append((block, heading))
        else:
            units.extend((piece, heading) for piece in _split_words(block, UNIT_TOKENS))
    return units


def _tail(text: str, tokens: int) -> str:
    words = text.split()
    tail: list[str] = []
    while words and estimate_tokens(" ".join([words[-1], *tail])) <= tokens:
        tail.insert(0, words.pop())
    return " ".join(tail)


def chunk_text(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    parts: list[str] = []
    heading: str | None = None
    fresh = False

    def emit() -> None:
        content = "\n\n".join(parts)
        chunks.append(Chunk(len(chunks), content, estimate_tokens(content), heading))

    for unit, unit_heading in _units(text):
        if parts and estimate_tokens("\n\n".join([*parts, unit])) > MAX_TOKENS:
            emit()
            parts = [_tail("\n\n".join(parts), OVERLAP_TOKENS)]
            fresh = False
        if not fresh:
            heading = unit_heading
            fresh = True
        parts.append(unit)
    if fresh:
        emit()
    return chunks
