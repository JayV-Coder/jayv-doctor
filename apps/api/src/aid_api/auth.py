"""Validação do JWT do Supabase Auth e exigência de MFA (`aal2`)."""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header

from aid_api.errors import ApiError

ALGORITHMS = ["ES256", "RS256"]
AUDIENCE = "authenticated"


@dataclass(frozen=True)
class Claims:
    sub: str
    email: str | None
    aal: str | None
    tenant_id: str | None
    tenant_role: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenVerifier:
    issuer: str

    def signing_key(self, token: str) -> Any:
        raise NotImplementedError

    def verify(self, token: str) -> Claims:
        raw = jwt.decode(
            token,
            self.signing_key(token),
            algorithms=ALGORITHMS,
            audience=AUDIENCE,
            issuer=self.issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
        return Claims(
            sub=raw["sub"],
            email=raw.get("email"),
            aal=raw.get("aal"),
            tenant_id=raw.get("tenant_id"),
            tenant_role=raw.get("tenant_role"),
            raw=raw,
        )


class JwksTokenVerifier(TokenVerifier):
    """Mantém um único PyJWKClient, para o cache de chaves durar entre requisições."""

    def __init__(self, issuer: str) -> None:
        super().__init__(issuer)
        self.client = jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json", cache_keys=True)

    def signing_key(self, token: str) -> Any:
        return self.client.get_signing_key_from_jwt(token).key


@lru_cache
def get_verifier() -> TokenVerifier:
    return JwksTokenVerifier(os.environ["SUPABASE_JWT_ISSUER"])


def unauthorized() -> ApiError:
    return ApiError(401, "unauthorized", "Sessão ausente ou expirada.")


# Síncrona de propósito: o FastAPI a roda no threadpool e o PyJWKClient faz I/O bloqueante.
def get_claims(
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> Claims:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized()
    try:
        return verifier.verify(token)
    except jwt.PyJWKClientConnectionError as exc:
        # Falha nossa, não do token: o cliente deve tentar de novo, não voltar ao login.
        raise ApiError(503, "auth_unavailable", "Autenticação indisponível.") from exc
    except jwt.PyJWTError as exc:
        raise unauthorized() from exc


def require_aal2(claims: Annotated[Claims, Depends(get_claims)]) -> Claims:
    if claims.aal != "aal2":
        raise ApiError(403, "mfa_required", "Esta ação exige verificação em duas etapas.")
    return claims
