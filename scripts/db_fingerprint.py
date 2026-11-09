"""Impressão digital do schema doctor para o drill de restauração (ticket #33): contagem por
tabela e um hash de amostra (as 1.000 primeiras linhas pela chave). `--until` considera só o que
foi criado até o ponto da restauração, para comparar a origem (tirada depois) com o projeto
restaurado nesse ponto.

Uso:
  SUPABASE_DB_URL=... uv run python scripts/db_fingerprint.py take [--until ISO] > origem.json
  uv run python scripts/db_fingerprint.py compare origem.json restaurado.json
"""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

SAMPLE = 1000
# Tabelas que mudam sozinhas entre a origem e o restaurado (relógio, filas, agregados): só a
# contagem até o ponto vale, a amostra não.
VOLATILE = {"outbox_messages", "idempotency_keys", "execution_stats_dirty", "usage_deltas"}


async def take(url: str, until: datetime | None) -> dict[str, dict[str, Any]]:
    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    found: dict[str, dict[str, Any]] = {}
    try:
        async with engine.begin() as connection:
            await connection.execute(text("set local transaction read only"))
            tables = (
                await connection.execute(
                    text(
                        "select c.relname,"
                        " exists (select 1 from pg_attribute a where a.attrelid = c.oid"
                        "   and a.attname = 'created_at' and not a.attisdropped) as dated,"
                        " exists (select 1 from pg_attribute a where a.attrelid = c.oid"
                        "   and a.attname = 'id' and not a.attisdropped) as keyed"
                        " from pg_class c where c.relnamespace = 'doctor'::regnamespace"
                        " and c.relkind in ('r', 'p') and not c.relispartition order by 1"
                    )
                )
            ).all()
            for table in tables:
                where = "where created_at <= :until" if until and table.dated else ""
                order = "id" if table.keyed else "t::text"
                params = {"until": until} if where else {}
                count = await connection.scalar(
                    text(f"select count(*) from doctor.{table.relname} t {where}"),
                    params,
                )
                sample = None
                if table.relname not in VOLATILE:
                    sample = await connection.scalar(
                        text(
                            "select md5(coalesce(string_agg(x, ',' order by n), '')) from ("
                            f" select t::text as x, row_number() over (order by {order}) as n"
                            f" from doctor.{table.relname} t {where}"
                            f" order by {order} limit {SAMPLE}) s"
                        ),
                        params,
                    )
                found[table.relname] = {"count": int(count or 0), "sample_md5": sample}
    finally:
        await engine.dispose()
    return found


def compare(source: dict[str, Any], restored: dict[str, Any]) -> list[str]:
    """O que difere entre a origem e o restaurado; vazio quando íntegro."""
    problems = []
    for table in sorted(set(source) | set(restored)):
        if table not in restored:
            problems.append(f"{table}: falta no restaurado")
        elif table not in source:
            problems.append(f"{table}: só no restaurado")
        elif source[table]["count"] != restored[table]["count"]:
            problems.append(
                f"{table}: {source[table]['count']} linhas na origem,"
                f" {restored[table]['count']} no restaurado"
            )
        elif source[table]["sample_md5"] != restored[table]["sample_md5"]:
            problems.append(f"{table}: amostra diferente")
    return problems


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    taking = commands.add_parser("take")
    taking.add_argument("--until", type=datetime.fromisoformat)
    comparing = commands.add_parser("compare")
    comparing.add_argument("source", type=Path)
    comparing.add_argument("restored", type=Path)
    args = parser.parse_args(argv)
    if args.command == "take":
        found = asyncio.run(take(os.environ["SUPABASE_DB_URL"], args.until))
        sys.stdout.write(json.dumps(found, indent=2, sort_keys=True) + "\n")
        return 0
    problems = compare(json.loads(args.source.read_text()), json.loads(args.restored.read_text()))
    for problem in problems:
        sys.stdout.write(f"{problem}\n")
    sys.stdout.write("íntegro\n" if not problems else f"{len(problems)} diferença(s)\n")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
