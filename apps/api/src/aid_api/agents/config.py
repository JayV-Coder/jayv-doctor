"""Coletas que um agente pode fazer (ticket #39): só da allowlist, sem consulta livre.

- `directory`: arquivos de exportação (SM58, SLG1, status de IDoc, NDJSON no contrato) numa
  pasta da máquina do agente; caminho absoluto, sem `..`, e um padrão simples de nome.
- `rfc_table`: leitura de tabela via RFC_READ_TABLE, só das tabelas e campos daqui.
- `rfc_function`: função customizada de leitura (ex.: SLG1, SM58), só com o prefixo `Z_AID_`.
"""

import re
from collections.abc import Mapping
from typing import Any

from aid_api.core.errors import ApiError

TABLES: dict[str, tuple[str, ...]] = {
    # Controle e status de IDoc (sem conteúdo de negócio).
    "EDIDC": (
        "DOCNUM",
        "STATUS",
        "DIRECT",
        "MESTYP",
        "IDOCTP",
        "RCVPRN",
        "SNDPRN",
        "CREDAT",
        "CRETIM",
        "UPDDAT",
        "UPDTIM",
    ),
    "EDIDS": (
        "DOCNUM",
        "LOGDAT",
        "LOGTIM",
        "COUNTR",
        "STATUS",
        "STAMQU",
        "STAMID",
        "STAMNO",
        "STATXT",
    ),
}
# Campos sem os quais o agente não monta o Evento (id, status e instante).
REQUIRED: dict[str, frozenset[str]] = {
    "EDIDC": frozenset({"DOCNUM", "STATUS", "UPDDAT", "UPDTIM"}),
    "EDIDS": frozenset({"DOCNUM", "STATUS", "COUNTR", "LOGDAT", "LOGTIM"}),
}
PATTERN = re.compile(r"^[A-Za-z0-9_.*?-]{1,64}$")
FUNCTION = re.compile(r"^Z_AID_[A-Z0-9_]{1,24}$")
MAX_COLLECTIONS = 10


def invalid(detail: str) -> ApiError:
    return ApiError(422, "invalid_config", f"Configuração inválida ({detail}).")


def validate(config: Mapping[str, Any]) -> dict[str, Any]:
    collections = config.get("collections")
    if not isinstance(collections, list) or len(collections) > MAX_COLLECTIONS:
        raise invalid(f"collections: lista com até {MAX_COLLECTIONS} coletas")
    interval = config.get("interval_seconds", 300)
    if not isinstance(interval, int) or not 60 <= interval <= 3600:
        raise invalid("interval_seconds: de 60 a 3600")
    clean = []
    for index, item in enumerate(collections):
        if not isinstance(item, Mapping):
            raise invalid(f"collections[{index}]: objeto")
        kind = item.get("type")
        if kind == "directory":
            path = str(item.get("path", ""))
            if not path.startswith("/") or ".." in path.split("/") or len(path) > 256:
                raise invalid(f"collections[{index}].path: caminho absoluto, sem '..'")
            if not PATTERN.match(str(item.get("pattern", "*.csv"))):
                raise invalid(f"collections[{index}].pattern: padrão simples de arquivo")
            if item.get("format", "csv") not in ("csv", "ndjson", "json"):
                raise invalid(f"collections[{index}].format: csv, ndjson ou json")
            clean.append(
                {
                    "type": "directory",
                    "path": path,
                    "pattern": item.get("pattern", "*.csv"),
                    "format": item.get("format", "csv"),
                }
            )
        elif kind == "rfc_table":
            table = str(item.get("table", ""))
            if table not in TABLES:
                raise invalid(f"collections[{index}].table: só {', '.join(TABLES)}")
            fields = item.get("fields") or list(TABLES[table])
            if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
                raise invalid(f"collections[{index}].fields: lista de nomes de campo")
            if not set(fields) <= set(TABLES[table]):
                raise invalid(f"collections[{index}].fields: só campos da allowlist de {table}")
            if not REQUIRED[table] <= set(fields):
                needed = ", ".join(sorted(REQUIRED[table]))
                raise invalid(f"collections[{index}].fields: inclua {needed}")
            rows = item.get("max_rows", 1000)
            if not isinstance(rows, int) or not 1 <= rows <= 5000:
                raise invalid(f"collections[{index}].max_rows: de 1 a 5000")
            clean.append(
                {"type": "rfc_table", "table": table, "fields": list(fields), "max_rows": rows}
            )
        elif kind == "rfc_function":
            name = str(item.get("name", ""))
            if not FUNCTION.match(name):
                raise invalid(f"collections[{index}].name: função customizada Z_AID_…")
            clean.append({"type": "rfc_function", "name": name})
        else:
            raise invalid(f"collections[{index}].type: directory, rfc_table ou rfc_function")
    return {"collections": clean, "interval_seconds": interval}
