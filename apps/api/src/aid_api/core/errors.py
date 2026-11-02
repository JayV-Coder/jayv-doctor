"""Erros RFC 7807 em pt-BR, com `code` estável para o cliente decidir o que fazer."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self, status: int, code: str, title: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(title)
        self.status = status
        self.code = code
        self.title = title
        self.headers = headers


def problem(
    status: int, code: str, title: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={"status": status, "code": code, "title": title},
        headers=headers,
    )


async def problem_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)  # noqa: S101
    return problem(exc.status, exc.code, exc.title, exc.headers)


# Sem os detalhes do Pydantic: eles ecoam a entrada, que pode trazer dados pessoais.
async def validation_handler(_: Request, __: Exception) -> JSONResponse:
    return problem(422, "validation_error", "Os dados enviados são inválidos.")


async def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("erro inesperado: %s %s", request.method, request.url.path, exc_info=exc)
    return problem(500, "internal_error", "Erro inesperado. Tente de novo.")


def install(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, problem_handler)
    app.add_exception_handler(RequestValidationError, validation_handler)
    app.add_exception_handler(Exception, unexpected_handler)
