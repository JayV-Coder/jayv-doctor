"""Formato do dataset (`tests/evaluation/datasets/*.jsonl`): um caso por linha, com os Eventos já
sanitizados e anonimizados, o gabarito e a origem do caso."""

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

System = Literal["sap", "salesforce", "gcp", "other"]


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["synthetic", "real"]
    # Sintético: a Regra ou o cenário que o gerou; real: o cliente e a autorização.
    rule: str | None = None
    scenario: str | None = None
    client: str | None = None
    authorized: bool | None = None


class CaseEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    execution_id: str
    timestamp: datetime
    severity: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    operation: str
    error: dict[str, Any] | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class Integration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    source_system: System
    target_system: System
    environment: Literal["prd", "hml", "dev"] = "prd"


class Label(BaseModel):
    """Gabarito do especialista. Sem causa identificável: `expected_inconclusive`, sem categoria."""

    model_config = ConfigDict(extra="forbid")

    category: str | None
    probable_cause: str | None
    responsible_system: System | None
    expected_inconclusive: bool
    labeled_by: str | None = None


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: Source
    integration: Integration
    events: list[CaseEvent]
    # Avaliação das Regras (INT-007 depende do instante em que a Execução foi avaliada).
    evaluated_at: datetime
    label: Label | None = None


def load(path: Path) -> list[Case]:
    with path.open(encoding="utf-8") as handle:
        return [Case.model_validate_json(line) for line in handle if line.strip()]


def dump(cases: Iterable[Case], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case.model_dump(mode="json"), ensure_ascii=False) + "\n")
