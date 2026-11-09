"""Quem fez a requisição, para a Trilha de auditoria (#28): IP, user agent e request id. O
middleware guarda; `tenant_tx` passa ao banco em `doctor.request`, e o trigger de `audit_logs`
preenche os registros da transação."""

import json
import os
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from uuid import uuid4

from aid_observability import logs
from fastapi import FastAPI, Request, Response

_meta: ContextVar[dict[str, str] | None] = ContextVar("request_meta", default=None)
IP = re.compile(r"^[0-9A-Fa-f.:]{2,45}$")
# Quantos saltos do fim do X-Forwarded-For são proxies confiáveis. O balanceador do Cloud Run
# acrescenta o IP de quem conectou, então o último item é sempre verdadeiro (padrão 1); com a web
# (Next.js) na frente, repassando o IP do navegador, use 2. O que vem antes disso é declarado
# pelo cliente e não entra na auditoria.
TRUSTED_HOPS = max(1, int(os.environ.get("AID_TRUSTED_PROXY_HOPS", "1")))
REQUEST_ID = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def current() -> str | None:
    meta = _meta.get()
    return json.dumps(meta) if meta else None


def describe(request: Request) -> dict[str, str]:
    hops = [
        hop.strip() for hop in request.headers.get("x-forwarded-for", "").split(",") if hop.strip()
    ]
    peer = request.client.host if request.client else ""
    ip = hops[-TRUSTED_HOPS] if len(hops) >= TRUSTED_HOPS else (hops[0] if hops else peer)
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
        meta = describe(request)
        token = _meta.set(meta)
        try:
            # O request_id em todo log da requisição (#34); o tenant entra quando o JWT é lido.
            with logs.bind(request_id=meta["request_id"]):
                return await call_next(request)
        finally:
            _meta.reset(token)
