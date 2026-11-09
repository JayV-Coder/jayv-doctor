"""Limites da saúde da plataforma (ticket #34), numa fonte só: `limits.json`, lido aqui pelo
`/admin/health` e pelo Terraform, que gera um alerta do Cloud Monitoring por medida."""

import json
from collections.abc import Mapping
from importlib import resources
from typing import Any

LIMITS: dict[str, dict[str, Any]] = json.loads(
    resources.files("aid_observability").joinpath("limits.json").read_text()
)
RUNBOOKS = "docs/operations/runbooks/"


def evaluate(measures: Mapping[str, Any]) -> dict[str, Any]:
    """Medida ausente conta como fora do limite: sem dado não é "ok"."""
    checks: dict[str, Any] = {}
    for name, rule in LIMITS.items():
        value = measures.get(name)
        checks[name] = {
            "value": None if value is None else float(value),
            "limit": rule["limit"],
            "ok": value is not None and float(value) <= float(rule["limit"]),
            "runbook": RUNBOOKS + rule["runbook"],
        }
    healthy = all(check["ok"] for check in checks.values())
    return {"status": "ok" if healthy else "degraded", "checks": checks, "measures": dict(measures)}
