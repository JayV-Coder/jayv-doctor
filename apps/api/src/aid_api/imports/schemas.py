"""Contratos das rotas de Importação manual."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["pending", "uploaded", "processing", "done", "failed", "rejected"]
Format = Literal["json", "ndjson", "csv"]


class NewImport(BaseModel):
    # `extra=forbid`: o tenant vem da claim; o caminho no Storage, do banco.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    integration_id: UUID
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)
    # Calculado no navegador; o worker confere de novo ao ler o Log bruto.
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CreatedImport(BaseModel):
    id: str
    status: Status
    error: str | None
    duplicate_of: str | None
    # Só para Importação pendente: o navegador sobe o arquivo direto no Storage.
    upload_url: str | None


class Import(BaseModel):
    id: str
    integration_id: str
    filename: str
    size_bytes: int
    format: Format | None
    status: Status
    duplicate_of: str | None
    total_lines: int
    accepted: int
    rejected: int
    duplicates: int
    secrets_removed: int
    error: str | None
    created_at: datetime
