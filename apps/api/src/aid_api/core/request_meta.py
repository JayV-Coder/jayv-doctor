"""Quem fez a requisição, para a Trilha de auditoria (#28): IP, user agent e request id. O
middleware guarda; `tenant_tx` passa ao banco em `doctor.request`, e o trigger de `audit_logs`
preenche os registros da transação."""

import json
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from uuid import uuid4

from fastapi import FastAPI, Request, Response

_meta: ContextVar[dict[str, str] | None] = ContextVar("request_meta", default=None)
# O Cloud Run põe o IP do cliente no primeiro item de X-Forwarded-For.
IP = re.compile(r"^[0-9A-Fa-f.:]{2,45}$")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def current() -> str | None:
    meta = _meta.get()
    return json.dumps(meta) if meta else None


def describe(request: Request) -> dict[str, str]:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "")
    trace = request.headers.get("x-cloud-trace-context", "").split("/")[0]
    given = request.headers.get("x-request-id", "")
    request_id = given if REQUEST_ID.match(given) else trace if REQUEST_ID.match(trace) else ""
    meta = {"request_id": request_id or str(uuid4())}
    if IP.match(ip):
        meta["ip"] = ip
    agent = request.headers.get("user-agent", "")
    if agent:
        meta["user_agent"] = agent[:500]
    return meta


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def remember(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        token = _meta.set(describe(request))
        try:
            return await call_next(request)
        finally:
            _meta.reset(token)
