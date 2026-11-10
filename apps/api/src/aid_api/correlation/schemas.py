"""Mapa de identificadores entre sistemas de uma Integração (ticket #40)."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Espaços nas pontas saem antes de contar: " a" não passa por nome de 2 caracteres.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class Lookup(BaseModel):
    """Consulta de leitura no destino, feita pelo Conector na hora do Diagnóstico: o registro
    com `field` igual à chave existe? (ex.: `Order.OrderNumber` no Salesforce, `A_SalesOrder.
    PurchaseOrderByCustomer` num serviço OData do SAP)."""

    model_config = ConfigDict(extra="forbid")

    connector_id: UUID
    entity: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
    field: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
    status_field: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
    # Chave do registro no destino, para a Evidência (ex.: SalesOrder); o Salesforce usa o Id.
    id_field: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
    # Zeros à esquerda que o destino guarda (VBELN tem 10 dígitos) e o Mapa tirou.
    pad_left: int = Field(default=0, ge=0, le=35)


class MappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    keys: list[dict[str, Any]]
    window_minutes: int = Field(default=60, ge=1, le=1440)
    reconcile: bool = False
    lookup: Lookup | None = None


class MappingChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    keys: list[dict[str, Any]] | None = None
    window_minutes: int | None = Field(default=None, ge=1, le=1440)
    reconcile: bool | None = None
    lookup: Lookup | None = None
    # `lookup: null` explícito tira a consulta; ausente, não mexe.
    clear_lookup: bool = False


class CorrelationMapping(BaseModel):
    id: str
    integration_id: str
    name: str
    keys: list[dict[str, Any]]
    window_minutes: int
    reconcile: bool
    lookup: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
