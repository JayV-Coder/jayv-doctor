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


class Ticket(BaseModel):
    id: str
    provider: str
    status: Literal["creating", "open", "done", "failed"]
    external_key: str | None
    url: str | None
    external_status: str | None
    error: str | None
    created_at: datetime
    last_synced_at: datetime | None
