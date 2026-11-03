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
from aid_evaluation.harness import CATEGORIES, CaseResult, Judge, run
from aid_evaluation.metrics import Metrics, summarize, write_json
from aid_evaluation.report import render
from aid_evaluation.synthetic import generate

ROOT = Path(__file__).resolve().parents[4] / "tests" / "evaluation"
DATASETS = ROOT / "datasets"
# O sintético sai do gerador e é sobrescrito por ele; os casos reais ficam num arquivo próprio
# (`real-v1.jsonl`), que o gerador nunca toca.
SYNTHETIC = DATASETS / "synthetic-v1.jsonl"
REAL = DATASETS / "real-v1.jsonl"
BASELINE = ROOT / "baseline.json"
PRICES = ROOT / "prices.json"
TOLERANCE = 0.02


def guarded(provider: str) -> Any:
    from aid_diagnosis_engine.llm.client import GuardedLLM
    from aid_diagnosis_engine.llm.registry import provider_for

    chosen = provider_for(provider)
    return lambda: GuardedLLM(chosen)


def dataset(paths: list[str] | None) -> list[Case]:
    files = [Path(p) for p in paths] if paths else sorted(DATASETS.glob("*.jsonl"))
    return [case for path in files for case in load(path)]


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
        # O juiz só no híbrido: no rules_only a Causa é o texto fixo da Regra.
        results = await run(
            cases,
            cast("Any", mode),
            llm if mode == "hybrid" else None,
            referee if mode == "hybrid" else None,
        )
        metrics.append(summarize(mode, results, prices))
        everything += results
    return metrics, everything


def command_run(args: argparse.Namespace) -> None:
    cases = dataset(args.dataset)
    cases = cases[: args.limit] if args.limit else cases
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
    names = ", ".join(args.dataset) if args.dataset else "datasets/*.jsonl"
    report.write_text(render(cases, metrics, names, notes), encoding="utf-8")
    write_json(metrics, Path(args.json))
    Path(args.results).write_text(
        "\n".join(json.dumps(asdict(r), ensure_ascii=False) for r in results) + "\n",
        encoding="utf-8",
    )
    print(f"relatório: {report}")


GATED = ("category_accuracy", "inconclusive_rate")


def command_gate(args: argparse.Namespace) -> None:
    """Falha se a precisão de categoria ou o inconclusivo correto do rules_only cair mais de 2 p.p.
    contra a linha de base (um caso sem causa que passa a ganhar categoria também reprova)."""
    cases = dataset(args.dataset)
    [metrics], _ = asyncio.run(evaluate(cases, ["rules_only"], None, False))
    current = {name: getattr(metrics, name) or 0.0 for name in GATED}
    if args.update:
        BASELINE.write_text(json.dumps({"rules_only": current}, indent=2) + "\n", encoding="utf-8")
        print(f"linha de base: {current}")
        return
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["rules_only"]
    failed = False
    for name in GATED:
        print(f"{name}: {current[name]:.4f} (linha de base {baseline[name]:.4f})")
        if current[name] < baseline[name] - TOLERANCE:
            print(f"regressão acima de 2 p.p. em {name}")
            failed = True
    if failed:
        sys.exit(1)


def command_generate(args: argparse.Namespace) -> None:
    cases = generate(args.seed)
    dump(cases, Path(args.out))
    print(f"{len(cases)} casos em {args.out}")


YES = {"s", "sim", "y", "yes"}
SYSTEMS = ("sap", "salesforce", "gcp", "other")


def ask(prompt: str, default: str | None, choices: tuple[str, ...] | None = None) -> str:
    """Repete a pergunta até ter uma resposta válida (Enter usa o valor atual, se houver)."""
    while True:
        answer = input(f"{prompt} [{default or ''}]: ").strip() or (default or "")
        if choices is not None:
            answer = answer.upper() if choices == CATEGORIES else answer.lower()
            if answer in choices:
                return answer
            print(f"  use uma destas: {', '.join(choices)}")
            continue
        if answer:
            return answer
        print("  resposta obrigatória")


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
        default = "s" if current and current.expected_inconclusive else "n"
        no_cause = input(f"Sem causa identificável? (s/n) [{default}]: ").strip().lower() or default
        if no_cause in YES:
            case.label = Label(
                category=None,
                probable_cause=None,
                responsible_system=None,
                expected_inconclusive=True,
                labeled_by=args.who,
            )
        else:
            case.label = Label(
                category=ask("Categoria", current.category if current else None, CATEGORIES),
                probable_cause=ask("Causa provável", current.probable_cause if current else None),
                responsible_system=cast(
                    "Any",
                    ask(
                        "Sistema responsável",
                        current.responsible_system if current else None,
                        SYSTEMS,
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
    gen.add_argument("--out", default=str(SYNTHETIC))
    runner = commands.add_parser("run")
    runner.add_argument("--dataset", nargs="+", help="padrão: todos os datasets/*.jsonl")
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
    gate.add_argument("--dataset", nargs="+", help="padrão: todos os datasets/*.jsonl")
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
