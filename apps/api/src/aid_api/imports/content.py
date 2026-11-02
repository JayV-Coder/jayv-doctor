"""Confere se o começo do arquivo bate com a extensão (ticket #11): magic bytes e parse.

Lê só um trecho (a API não baixa 50 MB); o parse linha a linha fica com o worker de ingestão.
"""

import json

MISMATCH = "Conteúdo não corresponde ao formato"
EMPTY = "Arquivo vazio"
HEAD_BYTES = 65536

BOM = b"\xef\xbb\xbf"
DELIMITERS = (",", ";", "\t")
# Controles que não aparecem em texto: indicam arquivo binário renomeado.
ALLOWED_CONTROLS = {"\t", "\n", "\r"}


def decode(head: bytes, complete: bool) -> str | None:
    """UTF-8 ou, na falta, Latin-1 (exportações de SAP costumam vir assim)."""
    if b"\x00" in head:
        return None
    try:
        return head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # O trecho pode cortar um caractere de vários bytes no fim.
        if not complete and exc.start >= len(head) - 3:
            return head[: exc.start].decode("utf-8", errors="strict")
    text = head.decode("latin-1")
    if any(ord(char) < 32 and char not in ALLOWED_CONTROLS for char in text):
        return None
    return text


def check_json(text: str, complete: bool) -> bool:
    stripped = text.lstrip()
    if not stripped or stripped[0] not in "[{":
        return False
    if not complete:
        return True
    try:
        json.loads(stripped)
    except ValueError:
        return False
    return True


def check_ndjson(text: str, complete: bool) -> bool:
    first, newline, _ = text.lstrip().partition("\n")
    if not newline and not complete:
        # Primeira linha maior que o trecho: dá para ver só que começa como objeto.
        return first.startswith("{")
    try:
        return isinstance(json.loads(first), dict)
    except ValueError:
        return False


def check_csv(text: str) -> bool:
    header = text.lstrip().partition("\n")[0]
    if header.startswith(("{", "[", "<")):
        return False
    return any(delimiter in header for delimiter in DELIMITERS)


def check_head(file_format: str, head: bytes, size: int) -> str | None:
    """`None` se o trecho inicial é do formato declarado; senão, o motivo da recusa."""
    if size == 0:
        return EMPTY
    complete = len(head) >= size
    text = decode(head.removeprefix(BOM), complete)
    if text is None:
        return MISMATCH
    valid = {
        "json": lambda: check_json(text, complete),
        "ndjson": lambda: check_ndjson(text, complete),
        "csv": lambda: check_csv(text),
    }.get(file_format, lambda: False)()
    return None if valid else MISMATCH
