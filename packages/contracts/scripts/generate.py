"""Gera os artefatos derivados de schemas/*.json (modelos Pydantic e tipos TS).

Rode via `make contracts`. O CI regenera e falha se houver diferença.
"""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"
PY_PACKAGE = ROOT / "python" / "aid_contracts"
TS_GENERATED = ROOT / "src" / "generated"
BANNER = "Gerado a partir de schemas/{name}. Não edite: rode `make contracts`."


def run(*args: str) -> None:
    subprocess.run(args, check=True, cwd=ROOT, stdin=subprocess.DEVNULL)


def generate(schema: Path) -> None:
    banner = BANNER.format(name=schema.name)
    shutil.copyfile(schema, PY_PACKAGE / "schemas" / schema.name)
    run(
        *("datamodel-codegen", "--input", str(schema), "--input-file-type", "jsonschema"),
        *("--output", str(PY_PACKAGE / f"{schema.stem.replace('.', '_')}.py")),
        *("--output-model-type", "pydantic_v2.BaseModel", "--target-python-version", "3.12"),
        *("--output-datetime-class", "AwareDatetime", "--enum-field-as-literal", "all"),
        *("--extra-fields", "forbid", "--formatters", "ruff-format"),
        *("--use-annotated", "--field-constraints", "--use-standard-collections"),
        *("--use-union-operator", "--use-schema-description", "--use-field-description"),
        *("--use-double-quotes", "--disable-timestamp", "--custom-file-header", f"# {banner}"),
    )
    run("ruff", "check", "--fix", "--select", "I", "--quiet", str(PY_PACKAGE))
    ts_out = TS_GENERATED / f"{schema.stem}.ts"
    run(
        *("pnpm", "exec", "json2ts", "--input", str(schema), "--output", str(ts_out)),
        *("--bannerComment", f"/* {banner} */", "--additionalProperties", "false"),
    )
    run("pnpm", "exec", "prettier", "--write", str(ts_out))


def main() -> None:
    (PY_PACKAGE / "schemas").mkdir(exist_ok=True)
    TS_GENERATED.mkdir(exist_ok=True)
    for schema in sorted(SCHEMAS.glob("*.json")):
        generate(schema)


if __name__ == "__main__":
    main()
