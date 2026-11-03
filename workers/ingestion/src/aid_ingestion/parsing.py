"""Leitura do Log bruto por formato. Cada linha vira um registro (objeto) ou uma rejeição com o
número da linha e o motivo; nada aqui lança exceção por causa do conteúdo.

NDJSON e CSV são lidos linha a linha a partir dos bytes, e a codificação é decidida por linha
(UTF-8, senão Latin-1): um byte estranho numa linha não estraga os acentos do arquivo inteiro.
"""

import csv
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

BOM = b"\xef\xbb\xbf"
DELIMITERS = ",;\t"
# Célula grande (stack trace, payload embutido) é lida inteira; a Sanitização corta em 8 KB.
csv.field_size_limit(16 * 1024 * 1024)


@dataclass(frozen=True)
class Line:
    number: int
    record: dict[str, Any] | None = None
    reason: str | None = None


def decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def text_lines(data: bytes) -> Iterator[str]:
    """Linhas decodificadas uma a uma, sem copiar o arquivo inteiro para uma lista."""
    for raw in io.BytesIO(data.removeprefix(BOM)):
        yield decode(raw)


def read_ndjson(data: bytes) -> Iterator[Line]:
    for number, raw in enumerate(text_lines(data), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except ValueError:
            yield Line(number, reason="JSON inválido")
            continue
        if isinstance(value, dict):
            yield Line(number, record=value)
        else:
            yield Line(number, reason="linha não é um objeto JSON")


def read_json(data: bytes) -> Iterator[Line]:
    # Um documento JSON só se lê inteiro; o tamanho já é limitado a 50 MB na Importação.
    try:
        value = json.loads(decode(data.removeprefix(BOM)))
    except ValueError:
        yield Line(1, reason="JSON inválido")
        return
    items = value if isinstance(value, list) else [value]
    for number, item in enumerate(items, 1):
        if isinstance(item, dict):
            yield Line(number, record=item)
        else:
            yield Line(number, reason="item não é um objeto JSON")


def read_csv(data: bytes) -> Iterator[Line]:
    lines = text_lines(data)
    header = next(lines, "")
    delimiter = max(DELIMITERS, key=header.count)
    names = [name.strip() for name in next(csv.reader([header], delimiter=delimiter), [])]
    if not names:
        return
    reader = csv.reader(lines, delimiter=delimiter)
    while True:
        try:
            row = next(reader)
        except StopIteration:
            return
        except csv.Error:
            yield Line(reader.line_num + 1, reason="linha CSV malformada")
            continue
        number = reader.line_num + 1
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != len(names):
            yield Line(number, reason="número de colunas diferente do cabeçalho")
            continue
        yield Line(number, record=dict(zip(names, row, strict=True)))


def read_records(data: bytes, file_format: str) -> Iterator[Line]:
    readers = {"ndjson": read_ndjson, "json": read_json, "csv": read_csv}
    yield from readers[file_format](data)
