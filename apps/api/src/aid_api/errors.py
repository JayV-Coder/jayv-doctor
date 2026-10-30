"""Erros RFC 7807 em pt-BR, com `code` estável para o cliente decidir o que fazer."""

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, title: str) -> None:
        super().__init__(title)
        self.status = status
        self.code = code
        self.title = title


async def problem_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)  # noqa: S101
    return JSONResponse(
        status_code=exc.status,
        media_type="application/problem+json",
        content={"status": exc.status, "code": exc.code, "title": exc.title},
    )
