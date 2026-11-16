"""Nomes de coluna aceitos para cada campo do Contrato de evento.

O worker de ingestão reconhece um registro (Importação, agente, Conectores) pelos nomes daqui, na
ordem: o primeiro presente vence. A API usa os mesmos nomes para sugerir o mapeamento de colunas
de uma Integração (#11), e o mapeamento salvo põe a coluna escolhida no nome do contrato antes
da detecção.
"""

from collections.abc import Iterable, Mapping
from typing import Any

FIELDS: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "@timestamp", "datetime", "date", "ts", "data_hora", "data"),
    "severity": ("severity", "severidade", "level", "nivel", "log_level", "msgty", "type"),
    "operation": (
        "operation",
        "operacao",
        "bapi",
        "method",
        "action",
        "event",
        "evento",
        "endpoint",
    ),
    "execution_id": (
        "execution_id",
        "correlation_id",
        "message_id",
        "transaction_id",
        "docnum",
        "idoc",
    ),
    "trace_id": ("trace_id", "traceid", "trace"),
    "message": ("message", "mensagem", "msg", "error_message", "text", "texto"),
    "http_status": ("http_status", "status_code", "status", "http_code"),
    "error_code": ("error_code", "code", "codigo", "msgno"),
}


def suggest(columns: Iterable[str]) -> dict[str, str]:
    """Para cada campo, a primeira coluna do arquivo com um nome aceito; uma coluna serve a um
    campo só. Comparação sem diferença de maiúsculas e sem espaços nas pontas."""
    available = {column.strip().lower(): column for column in columns}
    used: set[str] = set()
    found: dict[str, str] = {}
    for field, names in FIELDS.items():
        for name in names:
            column = available.get(name)
            if column is not None and column not in used:
                found[field] = column
                used.add(column)
                break
    return found


def apply_mapping(record: Mapping[str, Any], mapping: Mapping[str, str]) -> Mapping[str, Any]:
    """O registro com cada coluna mapeada no nome do campo do contrato. A coluna escolhida vale
    mais que uma coluna com o próprio nome do campo; coluna ausente no registro é ignorada."""
    present = {field: column for field, column in mapping.items() if column in record}
    if not present:
        return record
    moved = set(present.values())
    result = {key: value for key, value in record.items() if key not in moved}
    for field, column in present.items():
        result[field] = record[column]
    return result
