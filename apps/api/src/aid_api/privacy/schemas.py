"""Contratos de retenção e LGPD (ticket #29)."""

from datetime import datetime
from typing import Annotated, Literal

from aid_security.sanitizer import compile_extra
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

DataClass = Literal["raw_logs", "events", "incidents", "audit"]


class Retention(BaseModel):
    data_class: DataClass
    days: int
    default_days: int
    min_days: int
    max_days: int


class Deletion(BaseModel):
    requested_at: datetime
    scheduled_for: datetime


AiProfile = Literal["standard", "br_region", "dedicated", "local"]


class AiCheck(BaseModel):
    """Última verificação diária do perfil (ADR-0018): os hosts e a região efetivos."""

    checked_at: datetime
    ok: bool
    # Falso só quando um host saiu do lugar do perfil (falha da chamada não conta).
    in_region: bool
    hosts: list[str]
    region: str | None
    detail: str | None


class Reindex(BaseModel):
    """Documentos prontos da Base e quantos já estão no modelo de embedding do perfil."""

    model: str
    total: int
    current: int


class PrivacySettings(BaseModel):
    retention: list[Retention]
    llm_enabled: bool
    llm_provider: Literal["anthropic", "vertex", "vertex_dedicated", "local"]
    ai_profile: AiProfile
    # Projeto do GCP com a capacidade dedicada (nulo: o da plataforma).
    ai_project: str | None
    ai_check: AiCheck | None
    reindex: Reindex
    deletion: Deletion | None


class RetentionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_class: DataClass
    days: int = Field(ge=1, le=3650)


class AiProfileChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # O dedicado e o local são contratados com a plataforma (a API recusa com 422).
    profile: AiProfile


class LlmChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class DeletionRequest(BaseModel):
    """O Owner digita o slug da Organização para confirmar."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    confirmation: str = Field(min_length=1, max_length=100)


class SubjectQuery(BaseModel):
    """A Referência de negócio do titular (ex.: nº do pedido ou CPF) no corpo; vira HMAC com a
    chave da Organização e nunca chega ao banco nem aos logs."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reference: str = Field(min_length=1, max_length=200)


class SubjectEvents(BaseModel):
    events: int
    first_seen: datetime | None
    last_seen: datetime | None


class SubjectErased(BaseModel):
    events_erased: int


# O tipo vira o marcador `[REMOVIDO:<tipo>]` nos Eventos.
PatternKind = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{1,30}$")]


class SanitizationRules(BaseModel):
    """Regras de Sanitização da Organização (#13), aplicadas antes de gravar o Evento."""

    model_config = ConfigDict(extra="forbid")

    extra_patterns: dict[PatternKind, str] = Field(default_factory=dict, max_length=20)
    detect_ips: bool = True
    allow_private_ips: bool = False

    @field_validator("extra_patterns")
    @classmethod
    def patterns_are_safe(cls, value: dict[str, str]) -> dict[str, str]:
        # A mesma conferência do Sanitizer: inválido, catastrófico ou que casa com vazio é recusado
        # aqui, em vez de virar um padrão ignorado no worker.
        for kind, pattern in value.items():
            compile_extra(kind, pattern)
        return value
