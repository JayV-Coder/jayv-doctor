"""Contratos das rotas de Organizações, Membros e Convites."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["owner", "admin", "analyst", "viewer"]


class Profile(BaseModel):
    full_name: str | None
    avatar_url: str | None
    locale: str


class Organization(BaseModel):
    id: str
    name: str
    slug: str
    role: str


class Me(BaseModel):
    id: str
    email: str | None
    aal: str | None
    profile: Profile | None
    organizations: list[Organization]
    active_tenant_id: str | None
    active_role: str | None


class NewOrganization(BaseModel):
    # `extra=forbid`: o payload nunca define tenant nem Papel.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=80)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
    segment: str = Field(min_length=2, max_length=80)
    llm_provider: Literal["anthropic", "vertex"]
    dpa_accepted: Literal[True]


class CreatedOrganization(BaseModel):
    id: str


class Member(BaseModel):
    id: str
    display_name: str | None
    email: str
    role: str
    mfa_enabled: bool


class Invitation(BaseModel):
    id: str
    email: str
    role: str
    expires_at: datetime


class NewInvitation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    role: Role


class RoleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role


# No corpo, não na URL como no ticket: caminho de requisição vai para os logs do Cloud Run.
class Acceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str


class CreatedInvitation(BaseModel):
    id: str


class AcceptedInvitation(BaseModel):
    tenant_id: str
