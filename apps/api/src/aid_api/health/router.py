"""`/healthz` diz se o processo responde; `/readyz` se ele alcança o banco."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from aid_api.core.db import get_engine
from aid_api.core.errors import ApiError

router = APIRouter(tags=["health"])

Readiness = Callable[[], Awaitable[None]]


async def database_ready() -> None:
    async with get_engine().connect() as connection:
        await connection.execute(text("select 1"))


def get_readiness() -> Readiness:
    return database_ready


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(check: Annotated[Readiness, Depends(get_readiness)]) -> dict[str, str]:
    try:
        await check()
    except (OSError, SQLAlchemyError) as exc:
        raise ApiError(503, "not_ready", "Banco de dados indisponível.") from exc
    return {"status": "ok"}
