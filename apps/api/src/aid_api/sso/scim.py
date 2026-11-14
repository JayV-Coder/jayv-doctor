"""SCIM 2.0 (RFC 7643/7644) para o IdP provisionar e desprovisionar Usuários (ticket #48).

Só o recurso `User`, com `userName` (o e-mail), `externalId` e `active`. O IdP autentica com o
token da Organização (`Authorization: Bearer`), que o banco guarda só como hash: é ele que diz
de qual Organização é o pedido. Desativar ou apagar tira o Vínculo e encerra as sessões."""

import re
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_api.core.db import anonymous_tx, sqlstate
from aid_api.core.rate_limit import TokenBucketLimiter, check_rate, get_limiter
from aid_api.core.tokens import token_hash

USER = "urn:ietf:params:scim:schemas:core:2.0:User"
LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR = "urn:ietf:params:scim:api:messages:2.0:Error"
PATCH = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
FILTER = re.compile(r'^\s*userName\s+eq\s+"([^"]{3,320})"\s*$', re.IGNORECASE)
MEDIA = "application/scim+json"
PAGE_MAX = 100

router = APIRouter(prefix="/scim/v2", include_in_schema=False)


class ScimError(Exception):
    def __init__(self, status_code: int, detail: str, scim_type: str | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.scim_type = scim_type


def error_response(error: ScimError) -> JSONResponse:
    body: dict[str, Any] = {"schemas": [ERROR], "status": str(error.status_code)}
    body["detail"] = error.detail
    if error.scim_type:
        body["scimType"] = error.scim_type
    return JSONResponse(body, status_code=error.status_code, media_type=MEDIA)


def unauthorized() -> ScimError:
    return ScimError(401, "Token SCIM inválido.")


class ScimRepository:
    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self.engine = engine

    async def call(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            async with anonymous_tx({}, self.engine) as connection:
                rows = (await connection.execute(text(sql), params)).mappings()
                return [dict(row) for row in rows]
        except DBAPIError as exc:
            if sqlstate(exc) == "DR106":
                raise unauthorized() from exc
            if sqlstate(exc) in {"23514", "22P02"}:
                raise ScimError(400, "Valor inválido.", "invalidValue") from exc
            raise

    async def users(
        self,
        digest: str,
        name: str | None,
        target: str | None,
        offset: int = 0,
        limit: int = PAGE_MAX,
    ) -> list[dict[str, Any]]:
        return await self.call(
            "select id::text, user_name, external_id, active, created_at, updated_at"
            " from doctor.scim_users(:h, :n, cast(:t as uuid), :o, :l)",
            {"h": digest, "n": name, "t": target, "o": offset, "l": limit},
        )

    async def count(self, digest: str, name: str | None) -> int:
        [row] = await self.call(
            "select doctor.scim_user_count(:h, :n) as total", {"h": digest, "n": name}
        )
        return int(row["total"])

    async def upsert(self, digest: str, name: str, external: str | None, active: bool) -> str:
        [row] = await self.call(
            "select doctor.scim_upsert_user(:h, :n, :e, :a)::text as id",
            {"h": digest, "n": name, "e": external, "a": active},
        )
        return str(row["id"])

    async def set_active(self, digest: str, target: str, active: bool) -> bool:
        [row] = await self.call(
            "select doctor.scim_set_active(:h, cast(:t as uuid), :a) as found",
            {"h": digest, "t": target, "a": active},
        )
        return bool(row["found"])

    async def delete(self, digest: str, target: str) -> bool:
        [row] = await self.call(
            "select doctor.scim_delete_user(:h, cast(:t as uuid)) as found",
            {"h": digest, "t": target},
        )
        return bool(row["found"])


def get_scim_repository() -> ScimRepository:
    return ScimRepository()


Repository = Annotated[ScimRepository, Depends(get_scim_repository)]


def bearer_digest(
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not 20 <= len(token) <= 200:
        raise unauthorized()
    digest = token_hash(token)
    check_rate(limiter, f"scim:{digest[:16]}")
    return digest


def resource(row: dict[str, Any], request: Request) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schemas": [USER],
        "id": row["id"],
        "userName": row["user_name"],
        "active": row["active"],
        "emails": [{"value": row["user_name"], "primary": True}],
        "meta": {
            "resourceType": "User",
            "created": row["created_at"].isoformat(),
            "lastModified": row["updated_at"].isoformat(),
            "location": str(request.url_for("scim_get_user", target=row["id"])),
        },
    }
    if row.get("external_id"):
        body["externalId"] = row["external_id"]
    return body


def scim_json(body: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status_code, media_type=MEDIA)


def user_name(payload: dict[str, Any]) -> str:
    name = payload.get("userName")
    if not isinstance(name, str) or not 3 <= len(name.strip()) <= 320 or "@" not in name:
        raise ScimError(400, "userName precisa ser o e-mail do Usuário.", "invalidValue")
    return name.strip().lower()


def active_of(payload: dict[str, Any]) -> bool:
    active = payload.get("active", True)
    if isinstance(active, str):
        active = active.lower() == "true"
    if not isinstance(active, bool):
        raise ScimError(400, "active precisa ser booleano.", "invalidValue")
    return active


def external_of(payload: dict[str, Any]) -> str | None:
    external = payload.get("externalId")
    return external[:200] if isinstance(external, str) else None


def patched_active(payload: dict[str, Any]) -> bool | None:
    """O `active` de um PatchOp: Entra ID manda `path: active`; Okta, o objeto em `value`."""
    operations = payload.get("Operations")
    if not isinstance(operations, list):
        raise ScimError(400, "PatchOp sem Operations.", "invalidSyntax")
    found: bool | None = None
    for operation in operations:
        if not isinstance(operation, dict) or str(operation.get("op", "")).lower() not in {
            "replace",
            "add",
        }:
            continue
        path = str(operation.get("path") or "")
        value = operation.get("value")
        if path.lower() == "active":
            found = active_of({"active": value})
        elif not path and isinstance(value, dict) and "active" in value:
            found = active_of(value)
    return found


@router.get("/ServiceProviderConfig")
async def service_provider_config() -> JSONResponse:
    return scim_json(
        {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
            "patch": {"supported": True},
            "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
            "filter": {"supported": True, "maxResults": 100},
            "changePassword": {"supported": False},
            "sort": {"supported": False},
            "etag": {"supported": False},
            "authenticationSchemes": [
                {
                    "type": "oauthbearertoken",
                    "name": "Bearer",
                    "description": "Token SCIM da Organização, gerado na tela de SSO.",
                }
            ],
        }
    )


@router.get("/Users")
async def list_users(
    request: Request,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
    authorization: Annotated[str | None, Header()] = None,
    filter_: Annotated[str | None, Query(alias="filter", max_length=400)] = None,
    start_index: Annotated[int, Query(alias="startIndex", ge=1)] = 1,
    count: Annotated[int, Query(ge=0, le=PAGE_MAX)] = PAGE_MAX,
) -> Response:
    try:
        digest = bearer_digest(limiter, authorization)
        name = None
        if filter_:
            match = FILTER.match(filter_)
            if not match:
                raise ScimError(400, 'Só o filtro userName eq "..." é aceito.', "invalidFilter")
            name = match.group(1).lower()
        # A página vem do banco, e o total à parte: o IdP reconcilia a lista inteira.
        total = await repository.count(digest, name)
        page = await repository.users(digest, name, None, start_index - 1, count)
    except ScimError as error:
        return error_response(error)
    return scim_json(
        {
            "schemas": [LIST],
            "totalResults": total,
            "startIndex": start_index,
            "itemsPerPage": len(page),
            "Resources": [resource(row, request) for row in page],
        }
    )


@router.get("/Users/{target}", name="scim_get_user")
async def get_user(
    target: UUID,
    request: Request,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    try:
        digest = bearer_digest(limiter, authorization)
        rows = await repository.users(digest, None, str(target))
        if not rows:
            raise ScimError(404, "Usuário não encontrado.")
    except ScimError as error:
        return error_response(error)
    return scim_json(resource(rows[0], request))


async def payload_of(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except ValueError as exc:
        raise ScimError(400, "JSON inválido.", "invalidSyntax") from exc
    if not isinstance(payload, dict):
        raise ScimError(400, "JSON inválido.", "invalidSyntax")
    return payload


@router.post("/Users")
async def create_user(
    request: Request,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    try:
        digest = bearer_digest(limiter, authorization)
        payload = await payload_of(request)
        name = user_name(payload)
        if await repository.users(digest, name, None):
            raise ScimError(409, "userName já provisionado.", "uniqueness")
        created = await repository.upsert(digest, name, external_of(payload), active_of(payload))
        [row] = await repository.users(digest, None, created)
    except ScimError as error:
        return error_response(error)
    return scim_json(resource(row, request), status.HTTP_201_CREATED)


@router.put("/Users/{target}")
async def replace_user(
    target: UUID,
    request: Request,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    try:
        digest = bearer_digest(limiter, authorization)
        payload = await payload_of(request)
        if not await repository.set_active(digest, str(target), active_of(payload)):
            raise ScimError(404, "Usuário não encontrado.")
        [row] = await repository.users(digest, None, str(target))
    except ScimError as error:
        return error_response(error)
    return scim_json(resource(row, request))


@router.patch("/Users/{target}")
async def patch_user(
    target: UUID,
    request: Request,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    try:
        digest = bearer_digest(limiter, authorization)
        active = patched_active(await payload_of(request))
        if active is not None and not await repository.set_active(digest, str(target), active):
            raise ScimError(404, "Usuário não encontrado.")
        rows = await repository.users(digest, None, str(target))
        if not rows:
            raise ScimError(404, "Usuário não encontrado.")
    except ScimError as error:
        return error_response(error)
    return scim_json(resource(rows[0], request))


@router.delete("/Users/{target}")
async def delete_user(
    target: UUID,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    try:
        digest = bearer_digest(limiter, authorization)
        if not await repository.delete(digest, str(target)):
            raise ScimError(404, "Usuário não encontrado.")
    except ScimError as error:
        return error_response(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
