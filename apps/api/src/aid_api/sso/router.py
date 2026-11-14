"""SSO corporativo (ticket #48). Configurar é do Owner com MFA; a descoberta pelo e-mail é
anônima, com limite por IP; o provisionamento é de quem acabou de entrar pelo IdP."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from aid_api.core.auth import Claims, get_claims, require_manager
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.rate_limit import TokenBucketLimiter, check_rate, get_limiter, rate_limit
from aid_api.core.request_meta import describe
from aid_api.sso.repo import SsoRepository, get_sso_repository
from aid_api.sso.schemas import (
    ScimToken,
    SsoConfigIn,
    SsoDiscovery,
    SsoDomain,
    SsoDomainIn,
    SsoGroupsIn,
    SsoProvisioned,
    SsoSettings,
)

router = APIRouter(
    prefix="/api/v1",
    tags=["sso"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)
# Sem sessão (tela de login): limite próprio, por IP.
public = APIRouter(prefix="/api/v1", tags=["sso"])
Owner = Annotated[Claims, Depends(require_manager("owner"))]
Repository = Annotated[SsoRepository, Depends(get_sso_repository)]


@router.get("/sso", response_model=SsoSettings)
async def get_sso(claims: Owner, repository: Repository) -> SsoSettings:
    return await repository.settings(claims)


@router.put("/sso", response_model=SsoSettings)
async def configure_sso(
    config: SsoConfigIn, claims: Owner, repository: Repository, _: Idempotent
) -> SsoSettings:
    return await repository.configure(claims, config)


@router.delete("/sso", status_code=status.HTTP_204_NO_CONTENT)
async def disable_sso(claims: Owner, repository: Repository, _: Idempotent) -> None:
    await repository.disable(claims)


@router.post("/sso/domains", response_model=SsoDomain, status_code=status.HTTP_201_CREATED)
async def add_domain(
    new: SsoDomainIn, claims: Owner, repository: Repository, _: Idempotent
) -> SsoDomain:
    return await repository.add_domain(claims, new.domain)


@router.post("/sso/domains/{target}/verify", status_code=status.HTTP_202_ACCEPTED)
async def verify_domain(target: UUID, claims: Owner, repository: Repository, _: Idempotent) -> None:
    # A consulta ao DNS é do worker `notifier`; a tela acompanha pelo `verified_at`.
    await repository.verify_domain(claims, str(target))


@router.delete("/sso/domains/{target}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_domain(target: UUID, claims: Owner, repository: Repository, _: Idempotent) -> None:
    await repository.remove_domain(claims, str(target))


@router.put("/sso/groups", response_model=SsoSettings)
async def set_groups(
    groups: SsoGroupsIn, claims: Owner, repository: Repository, _: Idempotent
) -> SsoSettings:
    return await repository.set_groups(claims, groups)


@router.post("/sso/scim-token", response_model=ScimToken)
async def rotate_scim_token(claims: Owner, repository: Repository, _: Idempotent) -> ScimToken:
    return await repository.rotate_scim_token(claims)


@router.post("/sso/provision", response_model=SsoProvisioned)
async def provision(
    claims: Annotated[Claims, Depends(get_claims)], repository: Repository
) -> SsoProvisioned:
    """Logo depois do login pelo IdP: cria ou ajusta o Vínculo pelo grupo e ativa a
    Organização. A web renova a sessão em seguida, para o token trazer as claims dela."""
    return await repository.provision(claims)


@public.get("/sso/discover", response_model=SsoDiscovery)
async def discover(
    request: Request,
    repository: Repository,
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
    email: Annotated[str, Query(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")],
) -> SsoDiscovery:
    check_rate(limiter, f"sso-discover:{describe(request).get('ip', 'unknown')}")
    return await repository.discover(email)
