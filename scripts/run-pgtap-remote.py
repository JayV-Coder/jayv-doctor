"""Monta um teste pgTAP em SQL puro para rodar num projeto Supabase via SQL editor ou MCP.

Inlina os `\\ir` (que só o psql entende), troca o `rollback` final por um `select` que agrega
a saída TAP e mantém a transação aberta, para que a chamada termine sem commit.

    python3 scripts/run-pgtap-remote.py supabase/tests/database/02_tenants_rls.test.sql
"""

import re
import sys
from pathlib import Path


def render(test: Path) -> str:
    sql = test.read_text(encoding="utf-8")
    sql = re.sub(
        r"^\\ir (\S+)$",
        lambda m: (test.parent / m.group(1)).read_text(encoding="utf-8"),
        sql,
        flags=re.M,
    )
    tap = (
        "create temp table _tap (n serial, line text);\n"
        "grant insert, select on _tap to public;\n"
        "grant usage on sequence _tap_n_seq to public;\n"
    )
    sql = sql.replace("begin;\n", "begin;\n" + tap, 1)
    sql = re.sub(r"^select \* from finish\(\);\nrollback;\s*$", "", sql, flags=re.M)
    assertions = r"plan|has_\w+|is|isnt|ok|results_eq|throws_ok|policies_are|is_empty|lives_ok"
    sql = re.sub(
        rf"^select ((?:{assertions})\()",
        r"insert into _tap (line) select \1",
        sql,
        flags=re.M,
    )
    return sql + (
        "insert into _tap (line) select * from finish();\n"
        "select string_agg(line, E'\\n' order by n) as tap from _tap;\n"
    )


if __name__ == "__main__":
    print(render(Path(sys.argv[1])))
