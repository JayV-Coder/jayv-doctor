"""Leitura do Log bruto por formato. Cada linha vira um registro (objeto) ou uma rejeição com o
número da linha e o motivo; nada aqui lança exceção por causa do conteúdo."""

import csv
import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

BOM = b"\xef\xbb\xbf"
DELIMITERS = ",;\t"


@dataclass(frozen=True)
class Line:
    number: int
    record: dict[str, Any] | None = None
    reason: str | None = None


def decode(data: bytes) -> str:
    """UTF-8, com ou sem BOM; senão Latin-1 (exportações do SAP), que aceita qualquer byte."""
    data = data.removeprefix(BOM)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def read_ndjson(text: str) -> Iterator[Line]:
    for number, raw in enumerate(text.splitlines(), 1):
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


def read_json(text: str) -> Iterator[Line]:
    try:
        value = json.loads(text)
    except ValueError:
        yield Line(1, reason="JSON inválido")
        return
    items = value if isinstance(value, list) else [value]
    for number, item in enumerate(items, 1):
        if isinstance(item, dict):
            yield Line(number, record=item)
        else:
            yield Line(number, reason="item não é um objeto JSON")


def read_csv(text: str) -> Iterator[Line]:
    header = text.partition("\n")[0]
    delimiter = max(DELIMITERS, key=header.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    columns = next(reader, None)
    if not columns:
        return
    names = [column.strip() for column in columns]
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != len(names):
            yield Line(reader.line_num, reason="número de colunas diferente do cabeçalho")
            continue
        yield Line(reader.line_num, record=dict(zip(names, row, strict=True)))


def read_records(data: bytes, file_format: str) -> Iterator[Line]:
    text = decode(data)
    readers = {"ndjson": read_ndjson, "json": read_json, "csv": read_csv}
    yield from readers[file_format](text)
