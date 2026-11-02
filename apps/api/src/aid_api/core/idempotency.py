"""`Idempotency-Key`: a mesma chave com o mesmo corpo devolve a resposta gravada, sem novo efeito.

Reserva, efeito e resposta gravada correm numa única transação. A unicidade da chave no Postgres
serializa as chamadas repetidas: a segunda espera a primeira terminar e então devolve a resposta
dela, ou executa de verdade se a primeira falhou. Erro, cancelamento ou falha ao gravar desfazem
tudo, então a chave nunca fica presa. A reserva só acontece depois das checagens de permissão e
de validação da rota, para uma resposta gravada não dispensar a permissão de quem repete.
"""

import functools
import hashlib
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, Request, Response
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from aid_api.core.auth import Claims, get_claims
from aid_api.core.db import request_tx
from aid_api.core.errors import ApiError


@dataclass
class Stored:
    request_hash: str
    status: int | None
    body: str | None


class IdempotencySession:
    async def reserve(self, key: str, request_hash: str) -> Stored | None:
        """Reserva a chave e devolve `None`, ou devolve a resposta gravada com ela."""
        raise NotImplementedError

    async def remember(self, key: str, status: int, body: str) -> None:
        raise NotImplementedError


class PostgresSession(IdempotencySession):
    def __init__(self, connection: AsyncConnection) -> None:
        self.connection = connection

    async def reserve(self, key: str, request_hash: str) -> Stored | None:
        # Limpeza preguiçosa e limitada: sem job no pg_cron, que é do jayv-coder (ADR-0009).
        await self.connection.execute(
            text(
                "delete from doctor.idempotency_keys where id in ("
                " select id from doctor.idempotency_keys"
                " where created_at < now() - interval '24 hours' limit 100)"
            )
        )
        inserted = await self.connection.scalar(
            text(
                "insert into doctor.idempotency_keys (tenant_id, key, request_hash)"
                " values (doctor.current_tenant_id(), :k, :h)"
                " on conflict (tenant_id, user_id, key) do nothing returning id"
            ),
            {"k": key, "h": request_hash},
        )
        if inserted is not None:
            return None
        result = await self.connection.execute(
            text(
                "select request_hash, response_status, response_body"
                " from doctor.idempotency_keys where key = :k and user_id = auth.uid()"
            ),
            {"k": key},
        )
        row = result.one()
        return Stored(row.request_hash, row.response_status, row.response_body)

    async def remember(self, key: str, status: int, body: str) -> None:
        await self.connection.execute(
            text(
                "update doctor.idempotency_keys set response_status = :s, response_body = :b"
                " where key = :k and user_id = auth.uid()"
            ),
            {"s": status, "b": body, "k": key},
        )


class IdempotencyStore:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self.engine = engine

    @asynccontextmanager
    async def session(self, claims: Claims) -> AsyncIterator[IdempotencySession]:
        async with request_tx(claims, self.engine) as connection:
            yield PostgresSession(connection)


def get_idempotency_store() -> IdempotencyStore:
    return IdempotencyStore()


@dataclass
class Pending:
    store: IdempotencyStore
    claims: Claims
    key: str
    request_hash: str


class ReplayError(Exception):
    def __init__(self, response: Response) -> None:
        super().__init__("resposta gravada")
        self.response = response


async def idempotency(
    request: Request,
    claims: Annotated[Claims, Depends(get_claims)],
    store: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=255)] = None,
) -> None:
    """Põe por último entre as dependências da rota: só marca a chave, quem reserva é a rota."""
    if idempotency_key is None or claims.tenant_id is None:
        return
    digest = hashlib.sha256(
        b"\0".join(
            [
                claims.sub.encode(),
                request.method.encode(),
                request.url.path.encode(),
                await request.body(),
            ]
        )
    ).hexdigest()
    request.state.idempotency = Pending(store, claims, idempotency_key, digest)


Idempotent = Annotated[None, Depends(idempotency)]


def reserving(endpoint: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Reserva a chave depois de todas as dependências e da validação, logo antes do efeito."""

    @functools.wraps(endpoint)
    async def wrapped(*args: Any, idempotency_request: Request, **kwargs: Any) -> Any:
        pending: Pending | None = getattr(idempotency_request.state, "idempotency", None)
        if pending is not None:
            stack: AsyncExitStack = idempotency_request.state.idempotency_stack
            session = await stack.enter_async_context(pending.store.session(pending.claims))
            stored = await session.reserve(pending.key, pending.request_hash)
            if stored is not None:
                if stored.request_hash != pending.request_hash:
                    raise ApiError(
                        422,
                        "idempotency_key_reused",
                        "Esta chave já foi usada em outra requisição.",
                    )
                raise ReplayError(
                    Response(
                        content=stored.body,
                        status_code=stored.status or 200,
                        media_type="application/json",
                    )
                )
            idempotency_request.state.idempotency_session = session
        return await endpoint(*args, **kwargs)

    signature = inspect.signature(endpoint)
    extra = inspect.Parameter(
        "idempotency_request", inspect.Parameter.KEYWORD_ONLY, annotation=Request
    )
    wrapped.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=[*signature.parameters.values(), extra]
    )
    return wrapped


class IdempotentRoute(APIRoute):
    def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        super().__init__(path, reserving(endpoint), **kwargs)

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            # Erro ou cancelamento saem por aqui e desfazem a transação, reserva incluída.
            async with AsyncExitStack() as stack:
                request.state.idempotency_stack = stack
                try:
                    response = await original(request)
                except ReplayError as replay:
                    return replay.response
                session: IdempotencySession | None = getattr(
                    request.state, "idempotency_session", None
                )
                if session is not None:
                    pending: Pending = request.state.idempotency
                    await session.remember(
                        pending.key, response.status_code, bytes(response.body).decode()
                    )
                return response

        return handler
