"""Jira Service Management (ticket #43)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["low", "medium", "high", "critical"]


def default_priorities() -> dict[Severity, str]:
    return {"critical": "Highest", "high": "High", "medium": "Medium", "low": "Low"}


class JiraConnection(BaseModel):
    status: Literal["pending", "active", "needs_reauth"]
    sites: list[dict[str, Any]]
    cloud_id: str | None
    site_url: str | None
    project_key: str | None
    issue_type: str | None
    priority_map: dict[str, str]
    custom_fields: dict[str, Any]
    sync_status: bool
    jira_webhook_expires_at: datetime | None
    last_error: str | None


class Authorization(BaseModel):
    url: str


class Callback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=4, max_length=2000)
    state: str = Field(min_length=20, max_length=200)


class JiraConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cloud_id: str = Field(min_length=1, max_length=64)
    project_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,19}$")
    issue_type: str = Field(min_length=1, max_length=60)
    priority_map: dict[Severity, str] = Field(default_factory=default_priorities)
    # Campos customizados com valor fixo; os ids seguem o padrão do Jira (`customfield_<n>`).
    custom_fields: dict[str, str | int | float | bool] = Field(default_factory=dict)
    sync_status: bool = True


System = Literal["sap", "salesforce", "gcp", "other"]


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    impact: int = Field(ge=1, le=3)
    urgency: int = Field(ge=1, le=3)


def default_weights() -> dict[Severity, Weights]:
    return {
        "critical": Weights(impact=1, urgency=1),
        "high": Weights(impact=2, urgency=1),
        "medium": Weights(impact=2, urgency=2),
        "low": Weights(impact=3, urgency=3),
    }


class ServiceNowConnection(BaseModel):
    status: Literal["pending", "active", "needs_reauth"]
    instance_url: str | None
    client_id: str | None
    impact_map: dict[str, Weights]
    assignment_groups: dict[str, str]
    default_group: str | None
    sync_status: bool
    last_error: str | None


class ServiceNowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Só instâncias da ServiceNow (o banco confere de novo).
    instance_url: str = Field(pattern=r"^https://[a-z0-9][a-z0-9-]{0,62}\.service-now\.com$")
    client_id: str = Field(min_length=1, max_length=200)
    # Obrigatório na primeira vez e quando a instância ou o client id mudam; vai para o Vault.
    client_secret: str | None = Field(default=None, min_length=1, max_length=500)
    impact_map: dict[Severity, Weights] = Field(default_factory=default_weights)
    # Sistema responsável → grupo de atendimento (nome ou sys_id).
    assignment_groups: dict[System, str] = Field(default_factory=dict)
    # Para "Indeterminado" e Sistemas sem grupo.
    default_group: str | None = Field(default=None, max_length=100)
    sync_status: bool = True
    # Gera outro endereço para a Business Rule (o anterior para de valer).
    rotate_hook: bool = False


class ServiceNowSaved(BaseModel):
    connection: ServiceNowConnection
    # Endereço do webhook para a Business Rule: só na primeira vez ou ao gerar outro.
    hook_url: str | None


class Ticket(BaseModel):
    id: str
    provider: Literal["jira", "servicenow"]
    status: Literal["creating", "open", "done", "failed"]
    external_key: str | None
    url: str | None
    external_status: str | None
    error: str | None
    assignment_group: str | None
    created_at: datetime
    last_synced_at: datetime | None
