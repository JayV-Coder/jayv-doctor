"""Contratos das rotas de Conectores. A credencial só entra: nenhum modelo de resposta a tem."""

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

Provider = Literal["fake", "gcp", "salesforce", "sap"]
# SecretStr: a credencial não aparece em repr, log nem mensagem de validação.
Credential = SecretStr
Interval = Field(default=None, ge=60, le=86400)


def strip_name(value: str | None) -> str | None:
    return value.strip() if value is not None else None


# Sem `str_strip_whitespace` no modelo: ele mexeria também na credencial (a quebra de linha no
# fim de uma chave PEM importa). Só o nome é aparado.
class NewConnector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    integration_id: UUID
    provider: Provider
    name: str = Field(min_length=2, max_length=80)
    config: dict[str, Any] = Field(default_factory=dict)
    credential: Credential = Field(min_length=1, max_length=16384)
    sync_interval_seconds: int | None = Interval

    _strip = field_validator("name", mode="before")(strip_name)


class ConnectorChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=80)
    config: dict[str, Any] | None = None
    sync_interval_seconds: int | None = Interval
    credential: Credential | None = Field(default=None, min_length=1, max_length=16384)

    _strip = field_validator("name", mode="before")(strip_name)

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        sent = self.model_dump(exclude_unset=True)
        if not sent:
            raise ValueError("nada a alterar")
        if any(value is None for value in sent.values()):
            raise ValueError("campo enviado não pode ser nulo")
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
    # `auth` (credencial recusada; volta com credencial nova) ou `manual`.
    paused_reason: str | None
    consecutive_failures: int
    sync_interval_seconds: int
    # Formato do provedor: o GCP grava `timestamp`; a tela mostra só ele.
    checkpoint: dict[str, Any] | None
    last_sync_at: datetime | None
    # Registros da última Sincronização terminada; `None` antes da primeira.
    last_sync_records: int | None
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
