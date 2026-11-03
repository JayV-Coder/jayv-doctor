"""Contratos da Trilha de auditoria (ticket #28)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["security", "diagnosis", "connectors", "data", "incidents"]


class AuditSearch(BaseModel):
    """Filtros no corpo (POST): o termo pode ser o e-mail de um Usuário."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str | None = Field(default=None, max_length=200)
    category: Category | None = None
    since: datetime | None = None
    until: datetime | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class AuditEntry(BaseModel):
    id: str
    occurred_at: datetime
    actor_type: Literal["user", "system", "worker"]
    actor_id: str | None
    # E-mail do ator, resolvido na leitura (o registro guarda só o id).
    actor_label: str | None
    action: str
    category: Category | None
    resource_type: str | None
    resource_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None


class AuditPage(BaseModel):
    items: list[AuditEntry]
    next_cursor: str | None
