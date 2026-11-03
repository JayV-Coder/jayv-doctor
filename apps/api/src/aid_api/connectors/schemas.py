"""Contratos das rotas de Conectores. A credencial só entra: nenhum modelo de resposta a tem."""

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

Provider = Literal["fake", "gcp", "salesforce", "sap"]
# SecretStr: a credencial não aparece em repr, log nem mensagem de validação.
Credential = SecretStr
Interval = Field(default=None, ge=60, le=86400)


class NewConnector(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    integration_id: UUID
    provider: Provider
    name: str = Field(min_length=2, max_length=80)
    config: dict[str, Any] = Field(default_factory=dict)
    credential: Credential = Field(min_length=1, max_length=16384)


class ConnectorChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=2, max_length=80)
    config: dict[str, Any] | None = None
    sync_interval_seconds: int | None = Interval
    credential: Credential | None = Field(default=None, min_length=1, max_length=16384)

    @model_validator(mode="after")
    def something(self) -> Self:
        if not self.model_dump(exclude_unset=True):
            raise ValueError("nada a alterar")
        return self


class ConnectionTest(BaseModel):
    """Teste de um Conector salvo: a credencial salva não sai do Vault (ADR-0006) e vem aqui."""

    model_config = ConfigDict(extra="forbid")

    credential: Credential = Field(min_length=1, max_length=16384)


class NewConnectionTest(ConnectionTest):
    """Teste antes de salvar (assistente de configuração)."""

    provider: Provider
    config: dict[str, Any] = Field(default_factory=dict)


class TestResult(BaseModel):
    ok: bool
    message: str


class Connector(BaseModel):
    id: str
    integration_id: str
    provider: str
    name: str
    config: dict[str, Any]
    status: str
    consecutive_failures: int
    sync_interval_seconds: int
    last_sync_at: datetime | None
    last_error: str | None
    next_run_at: datetime
    created_at: datetime


class ConnectorSync(BaseModel):
    id: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    records: int
    error: str | None
