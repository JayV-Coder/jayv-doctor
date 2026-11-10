"""Contratos dos tokens de ingestão e de POST /ingestion/events."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NewIngestionToken(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=80)
    integration_id: UUID


class CreatedIngestionToken(BaseModel):
    id: str
    # Mostrado uma vez só: o banco guarda o sha256.
    token: str
    prefix: str


class IngestionToken(BaseModel):
    id: str
    name: str
    integration_id: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class RejectedEvent(BaseModel):
    index: int
    reason: str


class IngestionResult(BaseModel):
    accepted: int
    rejected: list[RejectedEvent]


class AgentRegistration(BaseModel):
    """Registro do agente local (ticket #39): o token de uso único e a chave pública Ed25519
    (32 bytes em base64) que ele gerou na máquina do cliente."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=200)
    public_key: str = Field(min_length=44, max_length=44)
    version: str = Field(min_length=1, max_length=40)


class AgentRegistered(BaseModel):
    agent_id: str
    # Aparece só aqui: o agente guarda com permissão restrita.
    secret: str
    # Para o mTLS no balanceador; nulo onde a CA da plataforma não está configurada.
    certificate: str | None


class AgentUpdate(BaseModel):
    version: str
    url: str
    sha256: str
    signature: str


class AgentConfig(BaseModel):
    integration_id: str
    config: dict[str, Any]
    config_version: int
    update: AgentUpdate | None = None


class AgentLlmRequest(BaseModel):
    """Pedido ao modelo local (#46): o corpo de `POST /v1/chat/completions`, já sanitizado."""

    id: str
    request: dict[str, Any]


class AgentLlmResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A resposta do servidor do cliente, ou o erro (só um dos dois).
    response: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=500)
