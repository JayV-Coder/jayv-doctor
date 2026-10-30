#!/usr/bin/env python3
"""Cria labels, milestones e issues do backlog (docs/backlog/*.md) no GitHub.

Requer o GitHub CLI autenticado (`gh auth login`) com permissão de escrita no repositório.

Uso:
    python3 scripts/create-github-issues.py --dry-run
    python3 scripts/create-github-issues.py --repo JayV-Coder/jayv-doctor

O script é idempotente: issues cujo título já existe no repositório são reaproveitadas.
Referências `{{#NN}}` viram `#<número real>`; se a numeração prevista divergir da real,
uma segunda passada corrige os corpos.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKLOG = ROOT / "docs" / "backlog"
REF = re.compile(r"\{\{#(\d+)\}\}")
INDEX_TITLE = "Roadmap — Integration AI Doctor (índice do backlog)"

LABELS: dict[str, tuple[str, str]] = {
    "feature": ("1D76DB", "Funcionalidade entregável de ponta a ponta"),
    "chore": ("C5DEF5", "Fundação, infraestrutura ou processo"),
    "epic": ("5319E7", "Ticket de acompanhamento"),
    "frontend": ("0E8A16", "Next.js / PWA"),
    "backend": ("FBCA04", "FastAPI / workers"),
    "infra": ("BFD4F2", "GCP, Terraform, CI/CD"),
    "database": ("006B75", "Supabase Postgres, migrações, RLS"),
    "ai": ("D876E3", "LLM, RAG, avaliação"),
    "security": ("B60205", "Segurança e isolamento"),
    "lgpd": ("E99695", "Privacidade e LGPD"),
    "mobile": ("2FBFAE", "Impacto direto na experiência mobile first"),
    "M01-org": ("EDEDED", "M01 — Organizações"),
    "M02-connectors": ("EDEDED", "M02 — Conectores"),
    "M03-ingestion": ("EDEDED", "M03 — Ingestão e normalização"),
    "M04-correlation": ("EDEDED", "M04 — Correlação de execuções"),
    "M05-diagnosis": ("EDEDED", "M05 — Motor de diagnóstico"),
    "M06-incidents": ("EDEDED", "M06 — Dashboard e incidentes"),
    "M07-knowledge": ("EDEDED", "M07 — Base de conhecimento"),
    "M08-audit": ("EDEDED", "M08 — Relatórios e auditoria"),
    "P0": ("B60205", "Obrigatório na versão"),
    "P1": ("D93F0B", "Importante"),
    "P2": ("FBCA04", "Desejável"),
}


@dataclass
class Issue:
    key: str
    title: str
    labels: list[str]
    body: str
    milestone: str
    source: str
    number: int | None = None
    refs: set[str] = field(default_factory=set)


def parse_backlog() -> tuple[list[Issue], list[tuple[str, str]]]:
    issues: list[Issue] = []
    milestones: list[tuple[str, str]] = []
    for path in sorted(BACKLOG.glob("[0-9][0-9]-*.md")):
        text = path.read_text(encoding="utf-8")
        head, *blocks = re.split(r"(?=^<!-- issue: \d+ -->$)", text, flags=re.M)
        meta = dict(re.findall(r"^(milestone|description):\s*(.+)$", head, flags=re.M))
        milestones.append((meta["milestone"], meta.get("description", "")))
        for block in blocks:
            key = re.match(r"<!-- issue: (\d+) -->", block).group(1)
            header, body = block.split("\n---\n", 1)
            fields = dict(re.findall(r"^(title|labels):\s*(.+)$", header, flags=re.M))
            issues.append(
                Issue(
                    key=key,
                    title=fields["title"].strip(),
                    labels=[label.strip() for label in fields["labels"].split(",")],
                    body=body.strip(),
                    milestone=meta["milestone"],
                    source=path.relative_to(ROOT).as_posix(),
                    refs=set(REF.findall(body)),
                )
            )
    return issues, milestones


def validate(issues: list[Issue]) -> None:
    keys = {i.key for i in issues}
    errors = []
    if len(keys) != len(issues):
        errors.append("chaves de issue duplicadas")
    for i in issues:
        errors += [f"#{i.key}: referência inexistente {{{{#{r}}}}}" for r in i.refs - keys]
        errors += [f"#{i.key}: label desconhecida {lb}" for lb in i.labels if lb not in LABELS]
    if errors:
        sys.exit("Backlog inválido:\n  " + "\n  ".join(errors))


def gh(*args: str, input: str | None = None) -> str:
    result = subprocess.run(["gh", *args], input=input, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])} falhou:\n{result.stderr}")
    return result.stdout


def render(issue: Issue, numbers: dict[str, int], repo: str) -> str:
    body = REF.sub(lambda m: f"#{numbers[m.group(1)]}", issue.body)
    body = body.replace("{{repo}}", f"https://github.com/{repo}/blob/main")
    source_url = f"https://github.com/{repo}/blob/main/{issue.source}"
    footer = f"_Fonte: [`{issue.source}`]({source_url}) · ticket {issue.key} do backlog_"
    return f"{body}\n\n---\n{footer}"


def ensure_labels(repo: str) -> None:
    for name, (color, description) in LABELS.items():
        gh(
            "label",
            "create",
            name,
            "--repo",
            repo,
            "--color",
            color,
            "--description",
            description,
            "--force",
        )


def ensure_milestones(repo: str, milestones: list[tuple[str, str]]) -> None:
    existing = {
        m["title"] for m in json.loads(gh("api", f"repos/{repo}/milestones?state=all&per_page=100"))
    }
    for title, description in milestones:
        if title not in existing:
            gh(
                "api",
                "-X",
                "POST",
                f"repos/{repo}/milestones",
                "-f",
                f"title={title}",
                "-f",
                f"description={description}",
            )


def existing_issues(repo: str) -> dict[str, int]:
    out = gh(
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        "all",
        "--limit",
        "1000",
        "--json",
        "number,title",
    )
    return {i["title"]: i["number"] for i in json.loads(out)}


def create_issue(repo: str, issue: Issue, body: str) -> int:
    url = gh(
        "issue",
        "create",
        "--repo",
        repo,
        "--title",
        issue.title,
        "--milestone",
        issue.milestone,
        "--label",
        ",".join(issue.labels),
        "--body-file",
        "-",
        input=body,
    ).strip()
    return int(url.rsplit("/", 1)[-1])


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", default="JayV-Coder/jayv-doctor")
    parser.add_argument(
        "--dry-run", action="store_true", help="só valida e lista o que seria criado"
    )
    args = parser.parse_args()

    issues, milestones = parse_backlog()
    validate(issues)
    if args.dry_run:
        for title, _ in milestones:
            group = [i for i in issues if i.milestone == title]
            print(f"\n## {title} ({len(group)})")
            for i in group:
                print(f"  {i.key}  {i.title}  [{', '.join(i.labels)}]  deps→{sorted(i.refs)}")
        print(
            f"\n{len(issues)} issues + 1 índice, {len(milestones)} milestones, "
            f"{len(LABELS)} labels. Backlog válido."
        )
        return

    ensure_labels(args.repo)
    ensure_milestones(args.repo, milestones)
    known = existing_issues(args.repo)

    # Passada 1: cria na ordem do backlog, prevendo os números das próximas issues.
    numbers: dict[str, int] = {i.key: known[i.title] for i in issues if i.title in known}
    rendered_with: dict[str, dict[str, int]] = {}
    for idx, issue in enumerate(issues):
        if issue.key in numbers:
            issue.number = numbers[issue.key]
            print(f"= #{issue.number} {issue.title} (já existia)")
            continue
        guess = dict(numbers)
        nxt = max([*known.values(), *numbers.values()], default=0) + 1
        for upcoming in issues[idx:]:
            if upcoming.key not in guess:
                guess[upcoming.key] = nxt
                nxt += 1
        issue.number = create_issue(args.repo, issue, render(issue, guess, args.repo))
        numbers[issue.key] = issue.number
        rendered_with[issue.key] = guess
        print(f"+ #{issue.number} {issue.title}")

    # Passada 2: corrige corpos cuja previsão de números não se confirmou.
    for issue in issues:
        used = rendered_with.get(issue.key)
        if used and any(used[r] != numbers[r] for r in issue.refs):
            gh(
                "issue",
                "edit",
                str(issue.number),
                "--repo",
                args.repo,
                "--body-file",
                "-",
                input=render(issue, numbers, args.repo),
            )
            print(f"~ #{issue.number} referências corrigidas")

    # Índice do roadmap.
    lines = [
        "Índice do backlog do Integration AI Doctor. PRD: "
        f"[`docs/prd.md`](https://github.com/{args.repo}/blob/main/docs/prd.md) · "
        "Mockups: [canvas](https://claude.ai/artifact/KJnu4pFdbtiZgkuayGRpXz)",
    ]
    for title, description in milestones:
        lines += ["", f"### {title}", f"_{description}_", ""]
        lines += [f"- [ ] #{i.number} {i.title}" for i in issues if i.milestone == title]
    index_body = "\n".join(lines)
    if INDEX_TITLE in known:
        gh(
            "issue",
            "edit",
            str(known[INDEX_TITLE]),
            "--repo",
            args.repo,
            "--body-file",
            "-",
            input=index_body,
        )
        print(f"~ #{known[INDEX_TITLE]} índice atualizado")
    else:
        url = gh(
            "issue",
            "create",
            "--repo",
            args.repo,
            "--title",
            INDEX_TITLE,
            "--label",
            "epic",
            "--body-file",
            "-",
            input=index_body,
        )
        print(f"+ {url.strip()}")


if __name__ == "__main__":
    main()
