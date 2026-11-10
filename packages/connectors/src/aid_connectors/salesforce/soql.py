"""SOQL parametrizado e limitado (ticket #37): o construtor só aceita objetos, campos e filtros
da allowlist, com `LIMIT` obrigatório. Não existe SOQL livre: nem o Usuário nem a config montam
texto de consulta, só escolhem itens da lista, e todo valor de filtro sai escapado."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
CUSTOM_OBJECT = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}__c$")
RECORD_ID = re.compile(r"^[A-Za-z0-9]{15,18}$")
MAX_LIMIT = 2000
OPERATORS = ("=", "!=")


class QueryNotAllowedError(ValueError):
    """Pedido fora da allowlist: nada é enviado ao Salesforce."""


@dataclass(frozen=True)
class Source:
    """Uma fonte de Eventos: o objeto e os campos que o Doctor pode ler dele."""

    object: str
    fields: tuple[str, ...]
    timestamp_field: str


# Fontes padrão do Salesforce. O objeto de log de integração do cliente entra pela config.
APEX_LOG = Source(
    "ApexLog",
    (
        "Id",
        "SystemModstamp",
        "StartTime",
        "Operation",
        "Status",
        "Request",
        "DurationMilliseconds",
        "LogLength",
    ),
    "StartTime",
)
EVENT_LOG_FILE = Source(
    "EventLogFile",
    ("Id", "SystemModstamp", "LogDate", "EventType", "LogFileLength", "Interval"),
    "LogDate",
)


def integration_log(object_name: str, fields: Sequence[str], timestamp_field: str) -> Source:
    if not CUSTOM_OBJECT.match(object_name):
        raise QueryNotAllowedError("objeto de log precisa ser um objeto customizado (__c)")
    chosen = tuple(dict.fromkeys(["Id", "SystemModstamp", *fields]))
    if not all(IDENTIFIER.match(field) for field in chosen) or len(chosen) > 30:
        raise QueryNotAllowedError("campos inválidos")
    if timestamp_field not in chosen:
        raise QueryNotAllowedError("o campo de data precisa estar entre os campos")
    return Source(object_name, chosen, timestamp_field)


@dataclass(frozen=True)
class Filter:
    field: str
    operator: str
    value: str


def literal(value: str) -> str:
    """String do SOQL: aspas e barra escapadas, sem quebra de linha (não sai da string)."""
    if any(char in value for char in "\r\n\x00") or len(value) > 255:
        raise QueryNotAllowedError("valor de filtro inválido")
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def stamp(moment: datetime) -> str:
    return (
        moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"
    )


def select(
    source: Source,
    allowlist: Mapping[str, Source],
    *,
    after: tuple[datetime, str] | None,
    limit: int,
    filters: Sequence[Filter] = (),
) -> str:
    """`SELECT … FROM <objeto da allowlist> WHERE SystemModstamp > … ORDER BY SystemModstamp, Id
    LIMIT n`. O Checkpoint é (SystemModstamp, Id): registros no mesmo instante desempatam pelo Id
    e nenhum se repete nem se perde ao retomar."""
    allowed = allowlist.get(source.object)
    if allowed is None or allowed != source:
        raise QueryNotAllowedError(f"objeto fora da allowlist: {source.object}")
    if not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise QueryNotAllowedError(f"LIMIT obrigatório, de 1 a {MAX_LIMIT}")
    conditions = []
    if after is not None:
        moment, record = after
        if not RECORD_ID.match(record):
            raise QueryNotAllowedError("Checkpoint inválido")
        conditions.append(
            f"(SystemModstamp > {stamp(moment)}"
            f" OR (SystemModstamp = {stamp(moment)} AND Id > {literal(record)}))"
        )
    for item in filters:
        if item.field not in source.fields or item.operator not in OPERATORS:
            raise QueryNotAllowedError(f"filtro fora da allowlist: {item.field}")
        conditions.append(f"{item.field} {item.operator} {literal(item.value)}")
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    # Tudo o que entra aqui saiu da allowlist ou de `literal`: não há texto livre.
    return (
        f"SELECT {', '.join(source.fields)} FROM {source.object}{where}"  # noqa: S608
        f" ORDER BY SystemModstamp, Id LIMIT {limit}"
    )
