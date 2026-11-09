"""Relatório do piloto (ticket #35): os números que o checklist da v0.1 pede, tirados do banco
para uma Organização e um período.

- **Precisão de categoria e de causa:** sobre os Diagnósticos revisados por humano. Aceito
  conta como certo nas duas; corrigido só na categoria conta a causa como certa, e vice-versa;
  rejeitado conta como errado nas duas.
- **Evidência rastreável:** Diagnósticos publicados com ao menos uma Evidência que aponta para
  um registro existente.
- **MTTR:** média de `resolved_at - first_seen_at` dos Incidentes resolvidos no período, contra a
  linha de base informada pelo cliente (`tenants.mttr_baseline_minutes`, as 4 semanas antes).
- **Vazamentos:** Evidências que apontam para Evento de outra Organização (as FKs compostas
  impedem; o número comprova).
- **Correções automáticas:** Recomendações executadas pela plataforma num sistema do cliente.
  Não existe caminho para isso (os Conectores só leem, e Recomendação é sempre ação humana); a
  contagem na trilha (`recommendation.*`, `*.executed`) comprova o zero.

Uso: SUPABASE_DB_URL=... uv run python scripts/pilot_report.py <tenant_id> \\
       --since 2026-11-10 --until 2026-12-08 [--sus respostas.csv]
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sus_score import mean_score, read_answers


@dataclass(frozen=True)
class Review:
    verdict: str
    corrected_category: bool
    corrected_cause: bool
    seconds_to_review: float | None = None


def precision(reviews: Sequence[Review]) -> tuple[float | None, float | None]:
    """(precisão de categoria, precisão de causa), de 0 a 1."""
    if not reviews:
        return None, None
    category = sum(
        1
        for r in reviews
        if r.verdict == "accepted" or (r.verdict == "corrected" and not r.corrected_category)
    )
    cause = sum(
        1
        for r in reviews
        if r.verdict == "accepted" or (r.verdict == "corrected" and not r.corrected_cause)
    )
    return category / len(reviews), cause / len(reviews)


def utc(value: str) -> datetime:
    """Data do comando em UTC: sem fuso, o asyncpg usaria o da máquina e deslocaria o período."""
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%".replace(".", ",")


def minutes(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f} min"


async def measure(url: str, tenant: str, since: datetime, until: datetime) -> dict[str, Any]:
    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    params = {"t": tenant, "since": since, "until": until}
    try:
        async with engine.begin() as connection:
            await connection.execute(text("set local transaction read only"))
            # A revisão mais recente de cada Diagnóstico revisado no período.
            reviews = [
                Review(
                    row.verdict,
                    bool(row.category),
                    bool(row.cause),
                    None if row.took is None else float(row.took),
                )
                for row in await connection.execute(
                    text(
                        "select distinct on (f.diagnosis_id) f.verdict,"
                        " f.correct_category is not null and f.correct_category <> coalesce("
                        "   d.classification, '') as category,"
                        " f.correct_cause is not null as cause, f.time_to_review_s as took"
                        " from doctor.diagnosis_feedback f join doctor.diagnoses d"
                        " on d.tenant_id = f.tenant_id and d.id = f.diagnosis_id"
                        " where f.tenant_id = cast(:t as uuid)"
                        " and f.created_at >= :since and f.created_at < :until"
                        " order by f.diagnosis_id, f.created_at desc"
                    ),
                    params,
                )
            ]
            published, traceable = (
                await connection.execute(
                    text(
                        "select count(*), count(*) filter (where exists ("
                        "   select 1 from doctor.diagnosis_evidence e"
                        "   where e.tenant_id = d.tenant_id and e.diagnosis_id = d.id"
                        # Registro da própria Organização; a Base global não conta.
                        "   and coalesce(e.event_id, e.raw_log_object_id, e.chunk_id,"
                        "   e.rule_match_id) is not null))"
                        " from doctor.diagnoses d where d.tenant_id = cast(:t as uuid)"
                        # Inconclusivo e falha do LLM podem não ter Evidência de propósito.
                        " and d.status = 'published'"
                        " and d.published_at >= :since and d.published_at < :until"
                    ),
                    params,
                )
            ).one()
            mttr, resolved = (
                await connection.execute(
                    text(
                        "select avg(extract(epoch from resolved_at - first_seen_at) / 60),"
                        " count(*) from doctor.incidents where tenant_id = cast(:t as uuid)"
                        " and status = 'resolved' and resolved_at >= :since"
                        " and resolved_at < :until"
                        # Só os que começaram no piloto: o histórico importado puxaria a média.
                        " and first_seen_at >= :since"
                    ),
                    params,
                )
            ).one()
            baseline = await connection.scalar(
                text(
                    "select mttr_baseline_minutes from doctor.tenants where id = cast(:t as uuid)"
                ),
                params,
            )
            # Evidência de Evento sem o Evento na própria Organização (pela chave, com índice).
            # A FK composta impede o vazamento; o número comprova sem varrer outros tenants.
            leaks = await connection.scalar(
                text(
                    "select count(*) from doctor.diagnosis_evidence e"
                    " where e.tenant_id = cast(:t as uuid) and e.event_id is not null"
                    " and not exists (select 1 from doctor.events v"
                    "   where v.tenant_id = e.tenant_id and v.id = e.event_id"
                    "   and v.timestamp = e.event_timestamp)"
                ),
                params,
            )
            automatic = await connection.scalar(
                text(
                    "select count(*) from doctor.audit_logs where tenant_id = cast(:t as uuid)"
                    " and occurred_at >= :since and occurred_at < :until"
                    " and actor_type in ('system', 'worker')"
                    " and (resource_type = 'recommendation' or action like '%.executed')"
                ),
                params,
            )
    finally:
        await engine.dispose()
    return {
        "reviews": reviews,
        "published": int(published),
        "traceable": int(traceable),
        "mttr": None if mttr is None else float(mttr),
        "resolved": int(resolved),
        "baseline": None if baseline is None else float(baseline),
        # Uma revisão por Diagnóstico (a mais recente), a mesma base da precisão.
        "review_times": [r.seconds_to_review for r in reviews if r.seconds_to_review is not None],
        "leaks": int(leaks or 0),
        "automatic": int(automatic or 0),
    }


def render(
    tenant: str,
    since: datetime,
    until: datetime,
    found: dict[str, Any],
    sus: float | None,
    respondents: int = 0,
) -> str:
    category, cause = precision(found["reviews"])
    traceable = found["traceable"] / found["published"] if found["published"] else None
    reduction = (
        1 - found["mttr"] / found["baseline"]
        if found["mttr"] is not None and found["baseline"]
        else None
    )
    times = found["review_times"]
    review = "—" if not times else f"mediana {median(times) / 60:.0f} min"
    period = f"{since:%d/%m/%Y} a {until:%d/%m/%Y}"
    rows = [
        (
            "Precisão de categoria",
            percent(category),
            f"{len(found['reviews'])} Diagnósticos revisados",
        ),
        ("Precisão de causa", percent(cause), "mesma base"),
        (
            "Diagnósticos com Evidência rastreável",
            percent(traceable),
            f"{found['published']} publicados",
        ),
        ("MTTR no piloto", minutes(found["mttr"]), f"{found['resolved']} Incidentes resolvidos"),
        (
            "MTTR de referência (4 semanas antes)",
            minutes(found["baseline"]),
            "informado pelo cliente",
        ),
        ("Redução de MTTR", percent(reduction), "meta da v0.1"),
        ("Tempo até a revisão humana", review, f"{len(times)} revisões"),
        ("Evidências sem registro da própria Organização", str(found["leaks"]), "meta: 0"),
        ("Correções automáticas", str(found["automatic"]), "meta: 0 (Recomendações são humanas)"),
        (
            "SUS (usabilidade)",
            "—" if sus is None else f"{sus:.1f}".replace(".", ","),
            f"{respondents} respondentes (mínimo 5)",
        ),
    ]
    lines = [
        f"# Relatório do piloto · {period}",
        "",
        f"Organização `{tenant}`. Gerado por `scripts/pilot_report.py`; a parte qualitativa"
        " fica nas seções seguintes do relatório.",
        "",
        "| Indicador | Valor | Base |",
        "|---|---|---|",
        *[f"| {name} | {value} | {base} |" for name, value, base in rows],
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tenant")
    parser.add_argument("--since", required=True, type=utc)
    parser.add_argument("--until", required=True, type=utc)
    parser.add_argument("--sus", type=Path)
    args = parser.parse_args(argv)
    found = asyncio.run(measure(os.environ["SUPABASE_DB_URL"], args.tenant, args.since, args.until))
    answers = read_answers(args.sus.read_text()) if args.sus else []
    sus = mean_score(answers)
    sys.stdout.write(render(args.tenant, args.since, args.until, found, sus, len(answers)))
    # Vazamento ou correção automática reprovam o piloto.
    return 1 if found["leaks"] or found["automatic"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
