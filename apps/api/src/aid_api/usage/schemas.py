"""Contratos de uso e Cotas (ticket #31)."""

from typing import Literal

from pydantic import BaseModel

Resource = Literal[
    "events_ingested", "diagnoses_llm", "storage_bytes", "connectors_active", "members"
]


class ResourceUsage(BaseModel):
    resource: Resource
    period: Literal["month", "none"]
    used: int
    quota: int
    ratio: float


class LlmUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    # Estimativa pela tabela de preços do worker; nula enquanto ela não estiver configurada.
    cost_estimate: float | None


class Usage(BaseModel):
    plan: Literal["pilot", "professional", "enterprise"]
    resources: list[ResourceUsage]
    llm: LlmUsage
