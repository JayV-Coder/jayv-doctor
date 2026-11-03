"""Harness de avaliação (ticket #30): dataset, métricas por modo e gate de regressão."""

import json
from pathlib import Path

import pytest
from aid_diagnosis_engine.llm.client import GuardedLLM
from aid_diagnosis_engine.llm.fake import FakeProvider
from aid_diagnosis_engine.llm.resilience import CircuitBreaker, RetryPolicy
from aid_evaluation.dataset import dump, load
from aid_evaluation.harness import run, run_case
from aid_evaluation.metrics import summarize
from aid_evaluation.report import render
from aid_evaluation.synthetic import generate

DATASET = Path(__file__).resolve().parents[3] / "tests" / "evaluation" / "datasets" / "v1.jsonl"


def test_dataset_v1_tem_120_casos_com_15_sem_causa_e_e_reproduzivel(tmp_path: Path) -> None:
    cases = generate()
    assert len(cases) >= 120
    assert sum(1 for case in cases if case.label and case.label.expected_inconclusive) >= 15
    assert {case.source.rule for case in cases} >= {f"INT-00{n}" for n in range(1, 9)}
    out = tmp_path / "v1.jsonl"
    dump(cases, out)
    assert load(out) == cases
    # O arquivo versionado é o que o gerador produz (nada editado à mão sem querer).
    assert load(DATASET) == generate()


@pytest.mark.asyncio
async def test_rules_only_classifica_e_respeita_o_inconclusivo() -> None:
    results = await run(generate(), "rules_only")
    metrics = summarize("rules_only", results)
    assert metrics.category_accuracy >= 0.85
    assert metrics.inconclusive_rate == 1.0
    assert metrics.false_inconclusive == 0
    assert metrics.hallucination_rate is None
    assert sum(metrics.confusion["AUTH"].values()) == 17


@pytest.mark.asyncio
async def test_hibrido_mede_alucinacao_juiz_tokens_e_custo() -> None:
    [case] = [c for c in generate() if c.id == "syn-timeout-00"]
    error = next(e for e in case.events if e.error)
    answer = {
        "classification": "UPSTREAM_TIMEOUT",
        "status": "IDENTIFIED",
        "probable_cause": "O SAP demorou além do timeout.",
        "confidence": 0.7,
        "responsible_system": case.integration.target_system,
        "evidence": [
            {"ref": error.id, "finding": "erro"},
            {"ref": "evt-inventado", "finding": "não existe"},
        ],
        "hypotheses": [],
        "recommendations": [],
        "requires_human_review": True,
    }
    provider = FakeProvider([json.dumps(answer)])
    llm = GuardedLLM(
        provider, breaker=CircuitBreaker(), policy=RetryPolicy(attempts=1, base_seconds=0)
    )
    judged: list[tuple[str, str]] = []

    async def judge(expected: str, proposed: str) -> bool:
        judged.append((expected, proposed))
        return True

    result = await run_case(case, "hybrid", llm, judge)
    assert result.predicted_category == "TIMEOUT"
    assert (result.discarded_evidence, result.cited_evidence) == (1, 2)
    assert result.cause_correct is True
    assert judged[0][1] == "O SAP demorou além do timeout."
    metrics = summarize(
        "hybrid", [result], {"fake-reasoning": {"input_per_mtok": 1.0, "output_per_mtok": 2.0}}
    )
    assert metrics.hallucination_rate == 0.5
    assert metrics.cause_accuracy == 1.0
    assert metrics.input_tokens > 0
    assert metrics.cost_usd is not None


@pytest.mark.asyncio
async def test_relatorio_tem_as_metricas_e_avisa_que_so_ha_sinteticos() -> None:
    cases = generate()
    metrics = summarize("rules_only", await run(cases, "rules_only"))
    text = render(cases, [metrics], "v1.jsonl", [])
    assert "| rules_only | 100,0%" in text
    assert "Matriz de confusão · rules_only" in text
    assert "Só casos sintéticos" in text
    assert "heurística (não calibrada)" in text
