"""Contratos das rotas de Integrações."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

System = Literal["sap", "salesforce", "gcp", "other"]
Environment = Literal["dev", "hml", "prd"]

Name = Field(min_length=2, max_length=80)
Description = Field(default=None, max_length=500)
OwnerTeam = Field(default=None, min_length=1, max_length=80)


class Integration(BaseModel):
    id: str
    name: str
    description: str | None
    source_system: System
    target_system: System
    owner_team: str | None
    environment: Environment
    archived_at: datetime | None
    created_at: datetime
    # Vem das Execuções (ticket #17). Até lá, `null`: sem Execução não há taxa, nem 0%.
    error_rate_24h: float | None = None


class NewIntegration(BaseModel):
    # `extra=forbid`: o payload nunca define tenant, autor nem arquivamento.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Name
    description: str | None = Description
    source_system: System
    target_system: System
    owner_team: str | None = OwnerTeam
    environment: Environment


class IntegrationChange(BaseModel):
    """Só os campos enviados mudam; `description` e `owner_team` aceitam `null` para limpar."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Description
    source_system: System | None = None
    target_system: System | None = None
    owner_team: str | None = OwnerTeam
    environment: Environment | None = None

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        sent = self.model_dump(exclude_unset=True)
        if not sent:
            raise ValueError("nada a alterar")
        required = ("name", "source_system", "target_system", "environment")
        if any(field in sent and sent[field] is None for field in required):
            raise ValueError("campo obrigatório não pode ser nulo")
        return self
