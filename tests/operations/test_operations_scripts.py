"""Scripts de operação do ticket #33: relatório de carga e impressão digital do banco."""

import importlib.util
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("INTEGRATION_DB_URL")


def script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load_report = script("load_report")
db_fingerprint = script("db_fingerprint")


def test_percentil_por_posicao() -> None:
    assert load_report.percentile([], 95) is None
    assert load_report.percentile(list(range(1, 101)), 95) == 95
    assert load_report.percentile([3.0], 95) == 3.0


def measured(**changes: object) -> object:
    base = {
        "accepted": 1000,
        "stored": 1000,
        "pending_batches": 0,
        "lag_p95_s": 12.0,
        "diagnoses": {"published": 100},
        "diagnosis_p95_s": 40.0,
        "read_p95_ms": 210.0,
        "error_rate": 0.0,
    }
    base.update(changes)
    return load_report.Measured(**base)


def test_relatorio_aponta_perda_e_lag_como_desvio() -> None:
    ok = load_report.render("carga-1", measured())
    assert "**desvio**" not in ok
    lost = load_report.verdicts(measured(stored=998))
    assert lost[0][2] is False
    slow = load_report.verdicts(measured(lag_p95_s=75.0))
    assert slow[1][2] is False
    pending = load_report.verdicts(measured(pending_batches=3))
    assert pending[0][2] is False
    unmeasured = load_report.verdicts(measured(read_p95_ms=None))
    assert unmeasured[2][2] is None


def test_resumo_do_k6_nos_dois_formatos() -> None:
    assert load_report.summary_value({"metrics": {"m": {"count": 7}}}, "m", "count") == 7
    nested = {"metrics": {"m": {"values": {"p(95)": 120.5}}}}
    assert load_report.summary_value(nested, "m", "p(95)") == 120.5
    assert load_report.summary_value({}, "m", "count") is None


def test_comparacao_acha_contagem_e_amostra_diferentes() -> None:
    source = {
        "events": {"count": 10, "sample_md5": "a"},
        "incidents": {"count": 2, "sample_md5": "b"},
    }
    assert db_fingerprint.compare(source, source) == []
    restored = {
        "events": {"count": 9, "sample_md5": "a"},
        "incidents": {"count": 2, "sample_md5": "c"},
    }
    assert db_fingerprint.compare(source, restored) == [
        "events: 10 linhas na origem, 9 no restaurado",
        "incidents: amostra diferente",
    ]
    assert db_fingerprint.compare(source, {"events": source["events"]}) == [
        "incidents: falta no restaurado"
    ]


@pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
@pytest.mark.asyncio
async def test_impressao_digital_do_banco_e_estavel() -> None:
    assert URL is not None
    until = datetime.now(UTC)
    first = await db_fingerprint.take(URL, until)
    second = await db_fingerprint.take(URL, until)
    assert "events" in first
    assert "incidents" in first
    assert db_fingerprint.compare(first, second) == []
