"""Contratos das rotas de Importação manual."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from aid_contracts.aliases import FIELDS
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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


class UploadUrl(BaseModel):
    # URL assinada do Storage: o navegador sobe o arquivo direto, com PUT, sem passar pela API.
    upload_url: str


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


# Mapeamento de colunas por Integração (#11): campo do Contrato de evento → coluna do arquivo.
ContractField = Literal[
    "timestamp",
    "severity",
    "operation",
    "execution_id",
    "trace_id",
    "message",
    "http_status",
    "error_code",
]
ColumnName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ImportMapping(BaseModel):
    columns: dict[ContractField, ColumnName]
    # Os campos do contrato e os nomes de coluna que cada um reconhece sem mapeamento.
    fields: dict[str, list[str]] = Field(
        default_factory=lambda: {field: list(names) for field, names in FIELDS.items()}
    )


class ImportMappingChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: dict[ContractField, ColumnName] = Field(max_length=8)


class MappingSuggestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # O cabeçalho do arquivo, lido no navegador.
    columns: list[Annotated[str, StringConstraints(max_length=200)]] = Field(max_length=500)


class MappingSuggestion(BaseModel):
    columns: dict[str, str]
