"""Logs JSON para o Cloud Logging, ligados ao trace e sem PII.

Só entram os campos desta lista (`FIELDS`), postos no contexto por quem atende a requisição ou a
mensagem; o resto (payload, e-mail, Referência) nunca vai para o log. Do traceback sai a lista de
parâmetros que o SQLAlchemy anexa (`[parameters: …]`), que pode trazer dado de cliente."""

import json
import logging
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from opentelemetry import trace

FIELDS = ("request_id", "tenant_id", "topic", "message_id", "worker")
# O que o SQLAlchemy e o asyncpg anexam com valores do cliente: os parâmetros do comando e o
# DETAIL do Postgres (`Key (email)=(ana@…) already exists`).
SCRUB = re.compile(r"^(\s*)(\[parameters: |DETAIL: |.*\bKey \().*$", re.MULTILINE)
_fields: ContextVar[dict[str, str] | None] = ContextVar("log_fields", default=None)


@contextmanager
def bind(**fields: str | None) -> Iterator[None]:
    """Campos do log enquanto o bloco roda (só os de `FIELDS`)."""
    current = {**(_fields.get() or {})}
    current.update({k: v for k, v in fields.items() if k in FIELDS and v})
    token = _fields.set(current)
    try:
        yield
    finally:
        _fields.reset(token)


def add(**fields: str | None) -> None:
    """Acrescenta campos ao contexto aberto por `bind` (a requisição toda), sem fechar nada."""
    current = _fields.get()
    if current is not None:
        current.update({k: v for k, v in fields.items() if k in FIELDS and v})


class JsonFormatter(logging.Formatter):
    def __init__(self, project: str | None = None) -> None:
        super().__init__()
        self.project = project or os.environ.get("GCP_PROJECT_ID")

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            **(_fields.get() or {}),
            # Campos estruturados de um log específico (`extra={"fields": {...}}`), sem dado do
            # cliente: ex. o host e a região de uma chamada de IA (ADR-0018).
            **(getattr(record, "fields", None) or {}),
        }
        span = trace.get_current_span().get_span_context()
        if span.is_valid and self.project:
            entry["logging.googleapis.com/trace"] = (
                f"projects/{self.project}/traces/{span.trace_id:032x}"
            )
            entry["logging.googleapis.com/spanId"] = f"{span.span_id:016x}"
        if record.exc_info:
            entry["exception"] = SCRUB.sub(
                r"\1[detalhe omitido]", self.formatException(record.exc_info)
            )
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str | None = None) -> None:
    """Um handler JSON na saída padrão (o Cloud Run manda para o Cloud Logging). Idempotente, e
    não tira os outros handlers (o `caplog` dos testes, por exemplo)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not isinstance(h.formatter, JsonFormatter)]
    root.handlers.append(handler)
    root.setLevel(level or os.environ.get("LOG_LEVEL", "INFO"))
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
