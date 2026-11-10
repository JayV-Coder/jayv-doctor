"""Diferença de qualidade e de custo entre perfis de IA (#45, ADR-0018): compara os JSONs de
métricas de `run --profile …` (um por perfil) contra o primeiro, modo a modo."""

import json
from pathlib import Path
from typing import Any

QUALITY = (
    ("category_accuracy", "Precisão de categoria", True),
    ("cause_accuracy", "Causa provável correta", True),
    ("inconclusive_rate", "Inconclusivo correto", True),
    ("hallucination_rate", "Evidência inventada", False),
)


def percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%".replace(".", ",")


def points(value: float | None, base: float | None) -> str:
    if value is None or base is None:
        return "—"
    return f"{(value - base) * 100:+.1f}".replace(".", ",") + " p.p."


def per_case(metrics: dict[str, Any]) -> float | None:
    cost, cases = metrics.get("cost_usd"), metrics.get("cases") or 0
    return None if cost is None or not cases else float(cost) / cases


def money(value: float | None) -> str:
    return "—" if value is None else f"US$ {value:.4f}".replace(".", ",")


def change(value: float | None, base: float | None) -> str:
    if value is None or base is None or base == 0:
        return "—"
    return f"{(value / base - 1) * 100:+.0f}%"


def render(reports: dict[str, dict[str, dict[str, Any]]]) -> str:
    """`reports`: perfil → (modo → métricas). O primeiro perfil é a referência."""
    names = list(reports)
    base_name = names[0]
    lines = [f"# Perfis de IA: qualidade e custo (referência: {base_name})", ""]
    modes = sorted({mode for report in reports.values() for mode in report})
    for mode in modes:
        lines += [f"## {mode}", "", "| Métrica | " + " | ".join(names) + " |"]
        lines.append("|---|" + "---|" * len(names))
        base = reports[base_name].get(mode, {})
        for key, label, _higher in QUALITY:
            cells = []
            for name in names:
                found = reports[name].get(mode, {}).get(key)
                cells.append(
                    percent(found)
                    if name == base_name
                    else f"{percent(found)} ({points(found, base.get(key))})"
                )
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
        cost_cells, latency_cells = [], []
        for name in names:
            metrics = reports[name].get(mode, {})
            cost = per_case(metrics)
            latency = metrics.get("latency_p95_ms")
            if name == base_name:
                cost_cells.append(money(cost))
                latency_cells.append("—" if latency is None else f"{latency:.0f} ms")
            else:
                cost_cells.append(f"{money(cost)} ({change(cost, per_case(base))})")
                latency_cells.append(
                    "—"
                    if latency is None
                    else f"{latency:.0f} ms ({change(latency, base.get('latency_p95_ms'))})"
                )
        lines.append("| Custo por Diagnóstico | " + " | ".join(cost_cells) + " |")
        lines.append("| Latência p95 | " + " | ".join(latency_cells) + " |")
        lines.append("")
    lines.append("Confiança e precisão são da avaliação offline (#30); a confiança é heurística.")
    return "\n".join(lines) + "\n"


def load(paths: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    """`perfil=arquivo.json`, na ordem dada."""
    reports: dict[str, dict[str, dict[str, Any]]] = {}
    for item in paths:
        name, _, path = item.partition("=")
        if not path:
            raise SystemExit(f"use perfil=arquivo.json, não {item}")
        reports[name] = json.loads(Path(path).read_text(encoding="utf-8"))
    return reports
