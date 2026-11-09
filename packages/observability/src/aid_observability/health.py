"""Limites da saúde da plataforma (ticket #34): os mesmos dos alertas do Cloud Monitoring
(`infrastructure/terraform/modules/observability`), avaliados no `/admin/health`."""

from collections.abc import Mapping
from typing import Any

# medida → (limite, runbook). Acima do limite, a plataforma está degradada.
LIMITS: dict[str, tuple[float, str]] = {
    "outbox_lag_seconds": (300, "docs/operations/runbooks/outbox-lag.md"),
    "outbox_stuck": (0, "docs/operations/runbooks/outbox-lag.md"),
    "ingestion_lag_seconds": (600, "docs/operations/runbooks/workers-parados.md"),
    "diagnosis_queue_seconds": (600, "docs/operations/runbooks/workers-parados.md"),
    "llm_error_rate_1h": (0.1, "docs/operations/runbooks/llm-erros.md"),
    "supabase_cpu_utilization": (0.8, "docs/operations/runbooks/supabase-cpu.md"),
}


def evaluate(measures: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        name: {
            "value": float(measures[name]),
            "limit": limit,
            "ok": float(measures[name]) <= limit,
            "runbook": runbook,
        }
        for name, (limit, runbook) in LIMITS.items()
        if measures.get(name) is not None
    }
    healthy = all(check["ok"] for check in checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks, "measures": dict(measures)}
