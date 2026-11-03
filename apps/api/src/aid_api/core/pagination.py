"""Cursor de paginação por (instante, id), opaco para o cliente: base64 de JSON."""

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from aid_api.core.errors import ApiError


def bad_cursor() -> ApiError:
    return ApiError(422, "invalid_cursor", "Cursor de paginação inválido.")


def encode_cursor(moment: datetime, target: str) -> str:
    raw = json.dumps([moment.isoformat(), target]).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        moment, target = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(moment), str(UUID(target))
    except (ValueError, TypeError, binascii.Error) as exc:
        raise bad_cursor() from exc
