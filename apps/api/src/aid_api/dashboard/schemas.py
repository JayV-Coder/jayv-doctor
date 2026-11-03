"""Contratos do Dashboard executivo (ticket #21)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Period = Literal["24h", "7d", "30d"]


class Kpi(BaseModel):
    value: float | None
    previous: float | None
    # Variação relativa ao período anterior (0,12 = +12%); None sem base de comparação.
    change: float | None


class Bucket(BaseModel):
    start: datetime
    total: int
    failed: int


class CategoryCount(BaseModel):
    category: str
    count: int


class IncidentRow(BaseModel):
    id: str
    number: int
    title: str
    severity: str
    status: str
    category: str
    integration_name: str
    environment: Literal["prd", "hml", "dev"]
    last_seen_at: datetime
    execution_count: int


class Dashboard(BaseModel):
    period: Period
    # Hora (24h) ou dia (7d, 30d), sempre em UTC.
    bucket: Literal["hour", "day"]
    executions: Kpi
    error_rate: Kpi
    mttr_minutes: Kpi
    open_incidents: int
    mttr_baseline_minutes: int | None
    # Variação do MTTR do período contra o baseline do piloto.
    mttr_vs_baseline: float | None
    failures: list[Bucket]
    failures_by_category: list[CategoryCount]
    critical_incident: IncidentRow | None
    recent_incidents: list[IncidentRow]
