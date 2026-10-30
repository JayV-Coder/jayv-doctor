# Gerado a partir de schemas/event.v1.json. Não edite: rode `make contracts`.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, RootModel, StringConstraints


class Attributes(RootModel[str]):
    root: Annotated[str, Field(max_length=200)]


class EventSource(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    provider: Literal["gcp", "salesforce", "sap", "aws", "azure", "mulesoft", "manual", "custom"]
    service: Annotated[str, Field(max_length=128, min_length=1)]
    resource: Annotated[str | None, Field(max_length=256, min_length=1)] = None


class EventError(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal[
        "TIMEOUT",
        "AUTH",
        "RATE_LIMIT",
        "VALIDATION",
        "BUSINESS_REJECTION",
        "DUPLICATE",
        "CONNECTIVITY",
        "UNKNOWN",
    ]
    http_status: Annotated[int | None, Field(ge=100, le=599)] = None
    code: Annotated[str | None, Field(max_length=128, min_length=1)] = None
    message: Annotated[str | None, Field(max_length=8192)] = None


class EventBusinessContext(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    entity_type: Annotated[str | None, Field(max_length=64, min_length=1)] = None
    entity_reference: Annotated[str | None, Field(max_length=256, min_length=1)] = None
    """
    Referência de negócio. Após a Sanitização é sempre persistida como hmac:<hex>.
    """


class EventV1(BaseModel):
    """
    Contrato de evento v1: formato canônico de todo Evento normalizado, independente da fonte. O tenant nunca vem no payload; é atribuído pela identidade autenticada do Conector ou do token de ingestão.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Annotated[str, Field(pattern="^1\\.(0|[1-9][0-9]{0,2})$")]
    """
    Versão do contrato. Major 1; o minor cresce em mudanças compatíveis.
    """
    event_id: Annotated[
        str, Field(pattern="^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    ]
    """
    UUIDv7 do Evento (ordenável pelo tempo).
    """
    integration_id: Annotated[str, Field(max_length=128, min_length=1)]
    """
    Identificador da Integração a que o Evento pertence.
    """
    execution_id: Annotated[str | None, Field(max_length=256, min_length=1)] = None
    """
    Identificador técnico da Execução, quando a fonte o fornece.
    """
    trace_id: Annotated[str | None, Field(max_length=256, min_length=1)] = None
    """
    Identificador de trace distribuído, quando houver.
    """
    timestamp: AwareDatetime
    """
    Instante do Evento em RFC 3339, com fuso e no máximo microssegundos.
    """
    source: EventSource
    operation: Annotated[str, Field(max_length=128, min_length=1)]
    """
    Operação de negócio ou técnica (ex.: create_order).
    """
    severity: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    error: EventError | None = None
    business_context: EventBusinessContext | None = None
    attributes: Annotated[
        dict[
            Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")],
            Attributes | int | float | bool | None,
        ]
        | None,
        Field(max_length=64),
    ] = None
    """
    Atributos planos (sem objetos aninhados). Os limites mantêm o bloco abaixo de 16 KB.
    """
