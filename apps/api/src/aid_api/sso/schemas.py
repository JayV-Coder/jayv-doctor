"""SSO corporativo por Organização (ticket #48): SAML 2.0, domínios, grupos e SCIM."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

SsoRole = Literal["admin", "analyst", "viewer"]
Domain = Annotated[
    str,
    # Minúsculas antes do formato: `ACME.com.br` é o mesmo domínio.
    BeforeValidator(lambda value: value.strip().lower() if isinstance(value, str) else value),
    StringConstraints(
        max_length=253, pattern=r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
    ),
]
GroupName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class SsoDomain(BaseModel):
    id: str
    domain: str
    verified_at: datetime | None
    # O TXT que prova o domínio: `_aid-sso.<domínio>` com `aid-sso=<token>`.
    txt_name: str
    txt_value: str


class SsoConnection(BaseModel):
    id: str
    status: Literal["pending_platform", "active", "error"]
    metadata_url: str
    require_sso: bool
    default_role: SsoRole | None
    last_error: str | None
    scim_enabled: bool
    updated_at: datetime


class SsoSettings(BaseModel):
    connection: SsoConnection | None
    domains: list[SsoDomain]
    groups: dict[str, SsoRole]


class SsoConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata_url: str = Field(max_length=500, pattern=r"^https://[^\s@]+$")
    require_sso: bool = False
    default_role: SsoRole | None = None


class SsoDomainIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: Domain


class SsoGroupsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: dict[GroupName, SsoRole] = Field(max_length=100)


class ScimToken(BaseModel):
    # Aparece só aqui: quem recebe cola no IdP. O banco guarda o hash.
    token: str
    base_url: str


class SsoDiscovery(BaseModel):
    """Para a tela de login: o domínio do e-mail tem SSO ativo? É obrigatório?"""

    sso: bool
    required: bool
    domain: str | None


class SsoProvisioned(BaseModel):
    tenant_id: str
    role: str
