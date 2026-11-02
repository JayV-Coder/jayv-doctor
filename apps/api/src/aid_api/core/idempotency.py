"""`Idempotency-Key`: a mesma chave com o mesmo corpo devolve a resposta gravada, sem novo efeito.

A chave é reservada antes da rota rodar, para duas chamadas simultâneas não executarem as duas.
Vale dentro de uma Organização ativa. Só respostas de sucesso ficam gravadas: em erro a chave é
liberada, e tentar de novo executa de verdade.
"""

import hashlib
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, Request, Response
from fastapi.routing import APIRoute
from sqlalchemy import text

from aid_api.core.auth import Claims, get_claims
from aid_api.core.db import tenant_tx
from aid_api.core.errors import ApiError

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class Stored:
    request_hash: str
    status: int | None
    body: str | None


class IdempotencyStore:
    async def reserve(self, claims: Claims, key: str, request_hash: str) -> Stored | None:
        """Reserva a chave e devolve `None`, ou devolve o que já existe com ela."""
        async with tenant_tx(claims) as connection:
            # 5 min em andamento: a instância caiu no meio. O efeito pode repetir, mas a chave não
            # fica presa por 24 h.
            await connection.execute(
                text(
                    "delete from doctor.idempotency_keys where key = :k and ("
                    "created_at < now() - interval '24 hours'"
                    " or (response_status is null and created_at < now() - interval '5 minutes'))"
                ),
                {"k": key},
            )
            inserted = await connection.scalar(
                text(
                    "insert into doctor.idempotency_keys (tenant_id, key, request_hash)"
                    " values (doctor.current_tenant_id(), :k, :h)"
                    " on conflict do nothing returning key"
                ),
                {"k": key, "h": request_hash},
            )
            if inserted is not None:
                return None
            result = await connection.execute(
                text(
                    "select request_hash, response_status, response_body"
                    " from doctor.idempotency_keys where key = :k"
                ),
                {"k": key},
            )
            row = result.one()
            return Stored(row.request_hash, row.response_status, row.response_body)

    async def remember(self, claims: Claims, key: str, status: int, body: str) -> None:
        async with tenant_tx(claims) as connection:
            await connection.execute(
                text(
                    "update doctor.idempotency_keys"
                    " set response_status = :s, response_body = :b where key = :k"
                ),
                {"s": status, "b": body, "k": key},
            )

    async def release(self, claims: Claims, key: str) -> None:
        async with tenant_tx(claims) as connection:
            await connection.execute(
                text("delete from doctor.idempotency_keys where key = :k"), {"k": key}
            )


def get_idempotency_store() -> IdempotencyStore:
    return IdempotencyStore()


class ReplayError(Exception):
    def __init__(self, response: Response) -> None:
        super().__init__("resposta gravada")
        self.response = response


@dataclass
class Reservation:
    store: IdempotencyStore
    claims: Claims
    key: str


async def idempotency(
    request: Request,
    claims: Annotated[Claims, Depends(get_claims)],
    store: Annotated[IdempotencyStore, Depends(get_idempotency_store)],
    idempotency_key: Annotated[str | None, Header(max_length=255)] = None,
) -> None:
    if idempotency_key is None or request.method in SAFE_METHODS or claims.tenant_id is None:
        return

    # O Usuário entra no hash: a resposta de uma pessoa não vai para outra da mesma Organização.
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

    stored = await store.reserve(claims, idempotency_key, digest)
    if stored is None:
        request.state.idempotency = Reservation(store, claims, idempotency_key)
        return
    if stored.request_hash != digest:
        raise ApiError(
            422, "idempotency_key_reused", "Esta chave já foi usada em outra requisição."
        )
    if stored.status is None:
        raise ApiError(409, "idempotency_in_progress", "Esta requisição ainda está em andamento.")
    raise ReplayError(
        Response(content=stored.body, status_code=stored.status, media_type="application/json")
    )


class IdempotentRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                response = await original(request)
            except ReplayError as replay:
                return replay.response
            except Exception:
                reservation = getattr(request.state, "idempotency", None)
                if reservation:
                    await reservation.store.release(reservation.claims, reservation.key)
                raise
            reservation = getattr(request.state, "idempotency", None)
            if reservation:
                await reservation.store.remember(
                    reservation.claims,
                    reservation.key,
                    response.status_code,
                    bytes(response.body).decode(),
                )
            return response

        return handler
