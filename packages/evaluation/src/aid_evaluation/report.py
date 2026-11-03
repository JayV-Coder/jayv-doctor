"""Relatório Markdown versionado (`tests/evaluation/reports/<data>.md`)."""

from datetime import date

from aid_evaluation.dataset import Case
from aid_evaluation.metrics import Metrics

TARGETS = {"category": 0.85, "cause": 0.75}


def pct(value: float | None) -> str:
    return "n/d" if value is None else f"{value * 100:.1f}%".replace(".", ",")


def ms(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def status(value: float | None, target: float) -> str:
    if value is None:
        return "não medido"
    return "atinge" if value >= target else "abaixo"


def render(cases: list[Case], metrics: list[Metrics], dataset: str, notes: list[str]) -> str:
    unlabeled = sum(1 for case in cases if case.label is None)
    # O cabeçalho conta só o que foi avaliado (caso sem gabarito fica de fora das métricas).
    cases = [case for case in cases if case.label is not None]
    synthetic = sum(1 for case in cases if case.source.kind == "synthetic")
    real = sum(1 for case in cases if case.source.kind == "real")
    no_cause = sum(1 for case in cases if case.label and case.label.expected_inconclusive)
    lines = [
        f"# Avaliação do motor de diagnóstico · {date.today().isoformat()}",
        "",
        f"Dataset `{dataset}`: **{len(cases)} casos** ({synthetic} sintéticos, {real} reais"
        f" anonimizados), {no_cause} sem causa identificável. A Confiança segue heurística (não"
        " calibrada): a calibração exige ≥ 500 casos reais rotulados"
        " (`docs/operations/avaliacao.md`).",
        "",
        "| Modo | Categoria | Causa provável | Inconclusivo correto | Inconclusivo indevido"
        " | Alucinação de Evidência | Falhas do LLM | Tokens (entrada/saída) | Custo"
        " | Latência p50/p95 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in metrics:
        category = f"{pct(item.category_accuracy)} ({item.category_correct}/{item.with_cause})"
        hits = f"{item.inconclusive_correct}/{item.expected_inconclusive}"
        inconclusive = f"{pct(item.inconclusive_rate)} ({hits})"
        lines.append(
            f"| {item.mode} | {category}"
            f" | {pct(item.cause_accuracy)} ({item.cause_correct}/{item.cause_judged})"
            f" | {inconclusive}"
            f" | {item.false_inconclusive}"
            f" | {pct(item.hallucination_rate)} ({item.discarded_evidence}/{item.cited_evidence})"
            f" | {item.llm_failures}"
            f" | {item.input_tokens}/{item.output_tokens}"
            f" | {'n/d' if item.cost_usd is None else f'US$ {item.cost_usd:.4f}'}"
            f" | {ms(item.latency_p50_ms)}/{ms(item.latency_p95_ms)} ms |"
        )
    lines += ["", "## Metas do piloto", ""]
    for item in metrics:
        category = status(item.category_accuracy, TARGETS["category"])
        cause = status(item.cause_accuracy, TARGETS["cause"])
        lines.append(
            f"- **{item.mode}:** categoria ≥ 85% — {category};"
            f" Causa provável ≥ 75% (quando há evidência) — {cause}."
        )
    for item in metrics:
        categories = sorted({*item.confusion, *(k for row in item.confusion.values() for k in row)})
        lines += [
            "",
            f"## Matriz de confusão · {item.mode}",
            "",
            "Linhas: gabarito; colunas: previsto (— = sem categoria / inconclusivo).",
            "",
            "| gabarito \\ previsto | " + " | ".join(categories) + " |",
            "|---|" + "---|" * len(categories),
        ]
        for expected in categories:
            row = item.confusion.get(expected, {})
            lines.append(
                f"| {expected} | " + " | ".join(str(row.get(c, 0)) for c in categories) + " |"
            )
        if item.providers:
            lines += ["", f"Provedor/modelo: {', '.join(item.providers)}."]
    if unlabeled:
        notes = [f"{unlabeled} casos sem gabarito ficaram de fora (rotule com `label`).", *notes]
    if real == 0:
        notes = [
            "Só casos sintéticos: eles são construídos a partir das próprias Regras, então o"
            " rules_only aqui mede que as Regras fazem o que documentam, não a precisão real."
            " A medida do piloto exige os casos reais anonimizados do cliente (≥ 40).",
            *notes,
        ]
    if notes:
        lines += ["", "## Observações", "", *[f"- {note}" for note in notes]]
    return "\n".join(lines) + "\n"
