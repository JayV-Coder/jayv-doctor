"""Validação do lote recebido de um sistema externo, antes de tocar o banco."""

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from aid_contracts.events import EventValidationError, validate_event
from fastapi import Request

from aid_api.core.errors import ApiError
from aid_api.ingestion.schemas import RejectedEvent

INGESTION_PREFIX = "aid_ing_"
MAX_EVENTS = 500
MAX_BYTES = 1024 * 1024
# Mesma janela da Importação: fora dela, um token criaria partições de anos arbitrários.
OLDEST = datetime(2000, 1, 1, tzinfo=UTC)
FUTURE_TOLERANCE = timedelta(days=1)


def new_token() -> tuple[str, str, str]:
    """(token, sha256, prefixo para a tela)."""
    token = INGESTION_PREFIX + secrets.token_urlsafe(32)
    return token, hash_token(token), token[:12]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def too_large() -> ApiError:
    return ApiError(413, "batch_too_large", f"Lote acima de {MAX_EVENTS} Eventos ou de 1 MB.")


def parse_batch(body: bytes) -> list[Any]:
    if len(body) > MAX_BYTES:
        raise too_large()
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise ApiError(422, "validation_error", "O corpo não é JSON.") from exc
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        raise ApiError(422, "validation_error", 'O corpo precisa ser {"events": [...]}.')
    if len(events) > MAX_EVENTS:
        raise too_large()
    # O tenant vem do token: payload que tenta defini-lo é recusado inteiro.
    if any(isinstance(item, dict) and "tenant_id" in item for item in events):
        raise ApiError(
            422, "tenant_id_not_allowed", "tenant_id não é aceito: o tenant vem do token."
        )
    return events


def in_window(timestamp: str, now: datetime) -> bool:
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return OLDEST <= moment <= now + FUTURE_TOLERANCE


def split(
    events: list[Any], integration_id: str, now: datetime | None = None
) -> tuple[list[dict[str, Any]], list[RejectedEvent]]:
    now = now or datetime.now(UTC)
    accepted: list[dict[str, Any]] = []
    rejected: list[RejectedEvent] = []
    for index, item in enumerate(events):
        if not isinstance(item, dict):
            rejected.append(RejectedEvent(index=index, reason="item não é um objeto JSON"))
            continue
        try:
            validate_event(item)
        except EventValidationError as exc:
            # Só os caminhos dos campos: a mensagem do validador ecoa os valores, que podem ter
            # dado pessoal antes da Sanitização.
            paths = sorted({error.split(":", 1)[0] for error in exc.errors})
            rejected.append(
                RejectedEvent(index=index, reason=f"fora do Contrato de evento: {', '.join(paths)}")
            )
            continue
        if item["integration_id"] != integration_id:
            rejected.append(RejectedEvent(index=index, reason="integration_id não é a do token"))
            continue
        if not in_window(item["timestamp"], now):
            rejected.append(RejectedEvent(index=index, reason="timestamp fora do intervalo aceito"))
            continue
        accepted.append(item)
    return accepted, rejected


async def read_limited(request: Request, limit: int = MAX_BYTES) -> bytes:
    """O corpo sem passar do limite na memória: recusa pelo Content-Length ou durante a leitura."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise too_large()
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise too_large()
    return bytes(body)
