"""CLI da avaliação (ticket #30).

python -m aid_evaluation generate            dataset sintético v1
python -m aid_evaluation run --modes rules_only hybrid --provider anthropic --judge
python -m aid_evaluation gate                gate de regressão (rules_only, 2 p.p.)
python -m aid_evaluation label ARQUIVO       rotulagem por especialista, caso a caso
python -m aid_evaluation sample RESULTADOS   amostra de 20% do juiz para conferência humana
"""

import argparse
import asyncio
import json
import random
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, cast

from aid_evaluation.dataset import Case, Label, dump, load
from aid_evaluation.harness import CaseResult, Judge, run
from aid_evaluation.metrics import Metrics, summarize, write_json
from aid_evaluation.report import render
from aid_evaluation.synthetic import generate

ROOT = Path(__file__).resolve().parents[4] / "tests" / "evaluation"
DATASET = ROOT / "datasets" / "v1.jsonl"
BASELINE = ROOT / "baseline.json"
PRICES = ROOT / "prices.json"
TOLERANCE = 0.02


def guarded(provider: str) -> Any:
    from aid_diagnosis_engine.llm.client import GuardedLLM
    from aid_diagnosis_engine.llm.registry import provider_for

    chosen = provider_for(provider)
    return lambda: GuardedLLM(chosen)


async def evaluate(
    cases: list[Case], modes: list[str], provider: str | None, judge: bool
) -> tuple[list[Metrics], list[CaseResult]]:
    llm = guarded(provider) if provider else None
    referee: Judge | None = None
    if judge and provider:
        from aid_evaluation.judge import LLMJudge

        referee = LLMJudge(guarded(provider)())
    prices = json.loads(PRICES.read_text(encoding="utf-8")) if PRICES.exists() else None
    metrics, everything = [], []
    for mode in modes:
        if mode == "hybrid" and llm is None:
            raise SystemExit("o modo hybrid precisa de --provider (anthropic ou vertex)")
        results = await run(cases, cast("Any", mode), llm if mode == "hybrid" else None, referee)
        metrics.append(summarize(mode, results, prices))
        everything += results
    return metrics, everything


def command_run(args: argparse.Namespace) -> None:
    cases = load(Path(args.dataset))[: args.limit] if args.limit else load(Path(args.dataset))
    metrics, results = asyncio.run(evaluate(cases, args.modes, args.provider, args.judge))
    notes = []
    if "hybrid" not in args.modes:
        notes.append(
            "Modo hybrid não rodado aqui: precisa do provedor real (job semanal do CI,"
            " `make eval-hybrid`)."
        )
    if not args.judge:
        notes.append("Causa provável sem juiz LLM nesta rodada (use --judge com --provider).")
    if not PRICES.exists():
        notes.append("Custo em aberto: preencha tests/evaluation/prices.json com a tabela oficial.")
    report = Path(args.report_dir) / f"{date.today().isoformat()}.md"
    report.write_text(render(cases, metrics, Path(args.dataset).name, notes), encoding="utf-8")
    write_json(metrics, Path(args.json))
    Path(args.results).write_text(
        "\n".join(json.dumps(asdict(r), ensure_ascii=False) for r in results) + "\n",
        encoding="utf-8",
    )
    print(f"relatório: {report}")


def command_gate(args: argparse.Namespace) -> None:
    """Falha se a precisão de categoria do rules_only cair mais de 2 p.p. contra a linha de base."""
    cases = load(Path(args.dataset))
    [metrics], _ = asyncio.run(evaluate(cases, ["rules_only"], None, False))
    if args.update:
        BASELINE.write_text(
            json.dumps({"rules_only": {"category_accuracy": metrics.category_accuracy}}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"linha de base: {metrics.category_accuracy:.4f}")
        return
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["rules_only"]["category_accuracy"]
    print(f"rules_only: {metrics.category_accuracy:.4f} (linha de base {baseline:.4f})")
    if metrics.category_accuracy < baseline - TOLERANCE:
        print("regressão acima de 2 p.p. na precisão de categoria")
        sys.exit(1)


def command_generate(args: argparse.Namespace) -> None:
    cases = generate(args.seed)
    dump(cases, Path(args.out))
    print(f"{len(cases)} casos em {args.out}")


def ask(prompt: str, default: str | None) -> str | None:
    answer = input(f"{prompt} [{default or ''}]: ").strip()
    return answer or default


def command_label(args: argparse.Namespace) -> None:
    """Rotulagem por especialista: mostra os Eventos e pergunta o gabarito; Enter mantém."""
    path = Path(args.dataset)
    cases = load(path)
    for case in cases:
        if case.label is not None and not args.review:
            continue
        print(f"\n== {case.id} · {case.integration.name} ({case.source.kind})")
        for event in case.events:
            error = event.error or ""
            print(f"  {event.timestamp:%H:%M:%S} {event.severity:8} {event.operation} {error}")
        current = case.label
        inconclusive = ask(
            "Sem causa identificável? (s/n)",
            "s" if current and current.expected_inconclusive else "n",
        )
        if inconclusive == "s":
            case.label = Label(
                category=None,
                probable_cause=None,
                responsible_system=None,
                expected_inconclusive=True,
                labeled_by=args.who,
            )
        else:
            case.label = Label(
                category=ask("Categoria", current.category if current else None),
                probable_cause=ask("Causa provável", current.probable_cause if current else None),
                responsible_system=cast(
                    "Any",
                    ask(
                        "Sistema (sap, salesforce, gcp, other)",
                        current.responsible_system if current else None,
                    ),
                ),
                expected_inconclusive=False,
                labeled_by=args.who,
            )
        dump(cases, path)


def command_sample(args: argparse.Namespace) -> None:
    """20% dos casos julgados, para uma pessoa conferir o veredito do juiz (CSV)."""
    rows = [
        json.loads(line)
        for line in Path(args.results).read_text(encoding="utf-8").splitlines()
        if line
    ]
    judged = [row for row in rows if row["cause_correct"] is not None]
    rng = random.Random(args.seed)  # noqa: S311 - amostragem, não segredo
    chosen = rng.sample(judged, max(1, round(len(judged) * 0.2))) if judged else []
    print("case_id,mode,juiz,gabarito,proposta,humano")
    for row in chosen:
        fields = [
            row["case_id"],
            row["mode"],
            str(row["cause_correct"]),
            row["expected_cause"] or "",
            row["probable_cause"] or "",
        ]
        print(",".join('"' + value.replace('"', "'") + '"' for value in fields) + ",")


def main() -> None:
    parser = argparse.ArgumentParser(prog="aid_evaluation")
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate")
    gen.add_argument("--seed", type=int, default=30)
    gen.add_argument("--out", default=str(DATASET))
    runner = commands.add_parser("run")
    runner.add_argument("--dataset", default=str(DATASET))
    runner.add_argument(
        "--modes", nargs="+", default=["rules_only"], choices=["rules_only", "hybrid"]
    )
    runner.add_argument("--provider", choices=["anthropic", "vertex"])
    runner.add_argument("--judge", action="store_true")
    runner.add_argument("--limit", type=int)
    runner.add_argument("--report-dir", default=str(ROOT / "reports"))
    runner.add_argument("--json", default=str(ROOT / "reports" / "latest.json"))
    runner.add_argument("--results", default=str(ROOT / "reports" / "latest-results.jsonl"))
    gate = commands.add_parser("gate")
    gate.add_argument("--dataset", default=str(DATASET))
    gate.add_argument("--update", action="store_true")
    label = commands.add_parser("label")
    label.add_argument("dataset")
    label.add_argument("--who", required=True)
    label.add_argument("--review", action="store_true")
    sample = commands.add_parser("sample")
    sample.add_argument("results")
    sample.add_argument("--seed", type=int, default=30)
    args = parser.parse_args()
    {
        "generate": command_generate,
        "run": command_run,
        "gate": command_gate,
        "label": command_label,
        "sample": command_sample,
    }[args.command](args)


if __name__ == "__main__":
    main()
