"""Métricas da avaliação, por modo: precisão de categoria (com a matriz de confusão), precisão da
Causa provável (pelo juiz), inconclusivo correto, "alucinação de Evidência", tokens, custo e
latência p50/p95."""

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aid_evaluation.harness import CaseResult

NONE = "—"


@dataclass
class Metrics:
    mode: str
    cases: int
    # Casos com causa identificável (o gabarito tem categoria).
    with_cause: int
    category_correct: int
    category_accuracy: float
    confusion: dict[str, dict[str, int]]
    cause_judged: int
    cause_correct: int
    cause_accuracy: float | None
    expected_inconclusive: int
    inconclusive_correct: int
    inconclusive_rate: float | None
    false_inconclusive: int
    cited_evidence: int
    discarded_evidence: int
    hallucination_rate: float | None
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    latency_p50_ms: float
    latency_p95_ms: float
    llm_failures: int = 0
    providers: list[str] = field(default_factory=list)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def cost(results: list[CaseResult], prices: dict[str, dict[str, float]] | None) -> float | None:
    """Preço por milhão de tokens, por modelo (`tests/evaluation/prices.json`), da tabela oficial
    do provedor; sem a tabela ou sem o modelo nela, o custo fica em aberto."""
    if not prices:
        return None
    total = 0.0
    for result in results:
        if result.input_tokens == 0 and result.output_tokens == 0:
            continue
        price = prices.get(result.model or "")
        if price is None:
            return None
        total += result.input_tokens / 1e6 * price["input_per_mtok"]
        total += result.output_tokens / 1e6 * price["output_per_mtok"]
    return round(total, 4)


def summarize(
    mode: str, results: list[CaseResult], prices: dict[str, dict[str, float]] | None = None
) -> Metrics:
    with_cause = [r for r in results if not r.expected_inconclusive]
    correct = sum(1 for r in with_cause if r.predicted_category == r.expected_category)
    confusion: dict[str, Counter[str]] = {}
    for result in results:
        expected = result.expected_category or NONE
        confusion.setdefault(expected, Counter())[result.predicted_category or NONE] += 1
    judged = [r for r in with_cause if r.cause_correct is not None]
    expected_inconclusive = [r for r in results if r.expected_inconclusive]
    cited = sum(r.cited_evidence for r in results)
    discarded = sum(r.discarded_evidence for r in results)
    latencies = [r.latency_ms for r in results]
    return Metrics(
        mode=mode,
        cases=len(results),
        with_cause=len(with_cause),
        category_correct=correct,
        category_accuracy=correct / len(with_cause) if with_cause else 0.0,
        confusion={key: dict(value) for key, value in sorted(confusion.items())},
        cause_judged=len(judged),
        cause_correct=sum(1 for r in judged if r.cause_correct),
        cause_accuracy=(sum(1 for r in judged if r.cause_correct) / len(judged))
        if judged
        else None,
        expected_inconclusive=len(expected_inconclusive),
        inconclusive_correct=sum(1 for r in expected_inconclusive if r.inconclusive),
        inconclusive_rate=(
            sum(1 for r in expected_inconclusive if r.inconclusive) / len(expected_inconclusive)
            if expected_inconclusive
            else None
        ),
        false_inconclusive=sum(1 for r in with_cause if r.inconclusive),
        cited_evidence=cited,
        discarded_evidence=discarded,
        hallucination_rate=(discarded / cited) if cited else None,
        input_tokens=sum(r.input_tokens for r in results),
        output_tokens=sum(r.output_tokens for r in results),
        cost_usd=cost(results, prices),
        latency_p50_ms=round(percentile(latencies, 0.5), 2),
        latency_p95_ms=round(percentile(latencies, 0.95), 2),
        llm_failures=sum(1 for r in results if r.llm_failed),
        providers=sorted({f"{r.provider}/{r.model}" for r in results if r.provider}),
    )


def write_json(metrics: list[Metrics], path: Path) -> None:
    path.write_text(
        json.dumps({m.mode: asdict(m) for m in metrics}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
