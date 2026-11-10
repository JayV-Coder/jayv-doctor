"""Diferença de qualidade e de custo entre perfis de IA (#45, ADR-0018) e entre modelos e
roteamentos (#47): compara os JSONs de métricas de `run` contra o primeiro, modo a modo, e diz
se cada variante pode ser adotada pelo critério do #47 (custo médio por Diagnóstico ao menos
30% menor, sem perder mais de 2 p.p. de precisão)."""

import json
from pathlib import Path
from typing import Any

QUALITY = (
    ("category_accuracy", "Precisão de categoria"),
    ("cause_accuracy", "Causa provável correta"),
    ("inconclusive_rate", "Inconclusivo correto"),
    # Aqui, menos é melhor.
    ("hallucination_rate", "Evidência inventada (menor é melhor)"),
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


SAVING = 0.30
TOLERANCE = 0.02
# A precisão que o critério confere (a Causa só conta se o juiz rodou nos dois).
GUARDED = ("category_accuracy", "cause_accuracy")


def failure_rate(metrics: dict[str, Any]) -> float:
    cases = metrics.get("cases") or 0
    return float(metrics.get("llm_failures") or 0) / cases if cases else 0.0


def recommend(base: dict[str, Any], candidate: dict[str, Any]) -> str:
    """Adotar ou não, com o motivo, pelo critério do #47: as duas precisões (categoria e Causa
    provável, com o mesmo juiz), no mesmo dataset, sem mais falhas do LLM, e o custo."""
    if base.get("cases") != candidate.get("cases"):
        return "datasets diferentes: rode as duas variantes nos mesmos casos"
    if base.get("judge") != candidate.get("judge"):
        return "juízes diferentes: rode as duas com o mesmo --judge-provider"
    if any(base.get(key) is None or candidate.get(key) is None for key in GUARDED):
        return "sem Causa provável medida nas duas: rode com --judge e o mesmo --judge-provider"
    losses = [(key, float(base[key]) - float(candidate[key])) for key in GUARDED]
    worst_key, worst = max(losses, key=lambda item: item[1])
    base_cost, cost = per_case(base), per_case(candidate)
    if base_cost is None or cost is None or base_cost == 0:
        return (
            "sem custo medido nas duas: preencha tests/evaluation/prices.json"
            " (open-weights: o custo do servidor por milhão de tokens)"
        )
    saving = 1 - cost / base_cost
    detail = f"custo {change(cost, base_cost)}, pior perda {points(-worst, 0.0)} em {worst_key}"
    # Arredondado: 0,90 - 0,88 é 0,020000000000000018 em ponto flutuante.
    if round(failure_rate(candidate) - failure_rate(base), 6) > TOLERANCE:
        return f"não adotar: mais falhas do LLM ({detail})"
    if round(worst, 6) > TOLERANCE:
        return f"não adotar: perda acima de 2 p.p. ({detail})"
    if round(saving, 6) < SAVING:
        return f"não adotar: economia abaixo de 30% ({detail})"
    return f"adotar ({detail})"


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
        for key, label in QUALITY:
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
        if mode == "hybrid" and len(names) > 1:
            lines += ["**Recomendação (critério do #47):**", ""]
            lines += [
                f"- {name}: {recommend(base, reports[name].get(mode, {}))}" for name in names[1:]
            ]
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
