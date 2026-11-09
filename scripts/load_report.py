"""Relatório de uma rodada de carga (ticket #33): confere no banco o que o k6 mediu do lado do
cliente. Zero perda (Eventos aceitos pela API = Eventos gravados com `attributes.load_run`),
lag de ingestão p95 < 60 s (gravação menos instante do Evento) e o tempo dos Diagnósticos.

Uso: SUPABASE_DB_URL=... uv run python scripts/load_report.py --run carga-1 \
       --since 2026-11-09T12:00:00Z [--ingestion ingestion-summary.json] [--read read-summary.json]
"""

import argparse
import asyncio
import json
import math
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

LAG_P95_SECONDS = 60.0
READ_P95_MS = 500.0
ERROR_RATE = 0.001


def percentile(values: Sequence[float], p: float) -> float | None:
    """Percentil por posição (nearest-rank), sem interpolação."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


@dataclass(frozen=True)
class Measured:
    accepted: int | None
    stored: int
    pending_batches: int
    lag_p95_s: float | None
    diagnoses: dict[str, int]
    diagnosis_p95_s: float | None
    read_p95_ms: float | None
    error_rate: float | None


def summary_value(summary: dict[str, Any], metric: str, field: str) -> float | None:
    found = summary.get("metrics", {}).get(metric, {})
    value = found.get(field, found.get("values", {}).get(field))
    return None if value is None else float(value)


def verdicts(measured: Measured) -> list[tuple[str, str, bool | None]]:
    """(meta, valor medido, atingiu?) — `None` quando a rodada não mediu aquela meta."""
    lost = None if measured.accepted is None else measured.accepted - measured.stored
    return [
        (
            "zero perda (aceitos = gravados)",
            "—" if lost is None else f"{measured.accepted} aceitos, {measured.stored} gravados",
            None if lost is None else lost == 0 and measured.pending_batches == 0,
        ),
        (
            "lag de ingestão p95 < 60 s",
            "—" if measured.lag_p95_s is None else f"{measured.lag_p95_s:.1f} s",
            None if measured.lag_p95_s is None else measured.lag_p95_s < LAG_P95_SECONDS,
        ),
        (
            "API de leitura p95 < 500 ms",
            "—" if measured.read_p95_ms is None else f"{measured.read_p95_ms:.0f} ms",
            None if measured.read_p95_ms is None else measured.read_p95_ms < READ_P95_MS,
        ),
        (
            "erros abaixo de 0,1%",
            "—" if measured.error_rate is None else f"{measured.error_rate * 100:.3f}%",
            None if measured.error_rate is None else measured.error_rate < ERROR_RATE,
        ),
    ]


def render(run: str, measured: Measured) -> str:
    lines = [f"# Carga · {run}", "", "| Meta | Medido | Resultado |", "|---|---|---|"]
    for goal, value, ok in verdicts(measured):
        result = "não medido" if ok is None else ("ok" if ok else "**desvio**")
        lines.append(f"| {goal} | {value} | {result} |")
    if measured.diagnoses:
        statuses = ", ".join(f"{key} {value}" for key, value in sorted(measured.diagnoses.items()))
        p95 = "—" if measured.diagnosis_p95_s is None else f"{measured.diagnosis_p95_s:.1f} s"
        lines += ["", f"Diagnósticos: {statuses}; fila até publicação p95 {p95}."]
    if measured.pending_batches:
        lines += ["", f"Lotes ainda na fila: {measured.pending_batches} (espere e rode de novo)."]
    return "\n".join(lines) + "\n"


async def measure(url: str, run: str, since: datetime) -> dict[str, Any]:
    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    try:
        async with engine.begin() as connection:
            stored, lags = 0, []
            for row in await connection.execute(
                text(
                    "select extract(epoch from ingested_at - timestamp)::float as lag"
                    " from doctor.events where timestamp >= :since"
                    " and attributes ->> 'load_run' = :run"
                ),
                {"since": since, "run": run},
            ):
                stored += 1
                lags.append(max(0.0, float(row.lag)))
            # Lote com falha permanente também é perda: entra como "na fila" até alguém olhar.
            failed = int(
                await connection.scalar(
                    text(
                        "select count(*) from doctor.ingestion_batches where created_at >= :since"
                        " and failed_at is not null"
                    ),
                    {"since": since},
                )
                or 0
            )
            pending = failed + int(
                await connection.scalar(
                    text(
                        "select count(*) from doctor.ingestion_batches where created_at >= :since"
                        " and processed_at is null and failed_at is null"
                    ),
                    {"since": since},
                )
                or 0
            )
            diagnoses: dict[str, int] = {}
            durations: list[float] = []
            for row in await connection.execute(
                text(
                    "select status, extract(epoch from published_at - created_at)::float as took"
                    " from doctor.diagnoses where created_at >= :since"
                ),
                {"since": since},
            ):
                diagnoses[row.status] = diagnoses.get(row.status, 0) + 1
                if row.took is not None:
                    durations.append(float(row.took))
    finally:
        await engine.dispose()
    return {
        "stored": stored,
        "lags": lags,
        "pending": pending,
        "diagnoses": diagnoses,
        "durations": durations,
    }


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--since", required=True, type=datetime.fromisoformat)
    parser.add_argument("--ingestion", type=Path)
    parser.add_argument("--read", type=Path)
    args = parser.parse_args(argv)
    found = asyncio.run(measure(os.environ["SUPABASE_DB_URL"], args.run, args.since))
    ingestion = json.loads(args.ingestion.read_text()) if args.ingestion else {}
    read = json.loads(args.read.read_text()) if args.read else {}
    accepted = summary_value(ingestion, "events_accepted", "count")
    failures = [
        value
        for value in (
            summary_value(ingestion, "http_req_failed", "value"),
            summary_value(read, "http_req_failed", "value"),
        )
        if value is not None
    ]
    measured = Measured(
        accepted=None if accepted is None else int(accepted),
        stored=found["stored"],
        pending_batches=found["pending"],
        lag_p95_s=percentile(found["lags"], 95),
        diagnoses=found["diagnoses"],
        diagnosis_p95_s=percentile(found["durations"], 95),
        read_p95_ms=summary_value(read, "http_req_duration", "p(95)"),
        error_rate=max(failures) if failures else None,
    )
    sys.stdout.write(render(args.run, measured))
    return 0 if all(ok is not False for _, _, ok in verdicts(measured)) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
