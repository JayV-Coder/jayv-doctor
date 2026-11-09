"""Medição do piloto (ticket #35): precisão pela revisão humana, SUS e o relatório no banco."""

import importlib.util
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("INTEGRATION_DB_URL")
sys.path.insert(0, str(ROOT / "scripts"))


def script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sus = script("sus_score")
pilot = script("pilot_report")


def test_sus_com_os_extremos_e_a_neutralidade() -> None:
    assert sus.score([5, 1] * 5) == 100
    assert sus.score([1, 5] * 5) == 0
    assert sus.score([3] * 10) == 50
    with pytest.raises(ValueError, match="10 notas"):
        sus.score([3] * 9)
    content = "q1,q2,q3,q4,q5,q6,q7,q8,q9,q10\n5,1,5,1,5,1,5,1,5,1\n3,3,3,3,3,3,3,3,3,3\n"
    assert sus.mean_score(sus.read_answers(content)) == 75


def test_precisao_de_categoria_e_de_causa_pela_revisao() -> None:
    reviews = [
        pilot.Review("accepted", False, False),
        pilot.Review("corrected", True, False),
        pilot.Review("corrected", False, True),
        pilot.Review("rejected", False, False),
    ]
    category, cause = pilot.precision(reviews)
    assert category == 0.5
    assert cause == 0.5
    assert pilot.precision([]) == (None, None)


@pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
@pytest.mark.asyncio
async def test_relatorio_do_piloto_contra_o_banco() -> None:
    assert URL is not None
    engine = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    tenant, integration, incident, diagnosis = (str(uuid4()) for _ in range(4))
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            for sql in (
                "insert into public.organizations (id, name, slug) values (:t, 'Piloto', :s)",
                "insert into doctor.tenants (id, mttr_baseline_minutes) values (:t, 120)",
                "insert into doctor.integrations (id, tenant_id, name, source_system,"
                " target_system, environment) values (:g, :t, 'Pedidos', 'salesforce', 'sap',"
                " 'prd')",
                "insert into doctor.incidents (id, tenant_id, integration_id, title, category,"
                " severity, rule_code, rule_version, first_seen_at, last_seen_at,"
                " execution_count, status, resolved_at, resolution_note) values (:i, :t, :g,"
                " 'Timeout', 'TIMEOUT', 'high', 'INT-003', '2026.10.1',"
                " cast(:at as timestamptz) - interval '30 min',"
                " :at, 1, 'resolved', :at, 'ok')",
                "insert into doctor.diagnoses (id, tenant_id, incident_id, version, status,"
                " stage, requested_mode, mode, processing_key, classification, published_at)"
                " values (:d, :t, :i, 1, 'published', 'done', 'rules_only', 'rules_only', :k,"
                " 'TIMEOUT', :at)",
                "insert into doctor.diagnosis_feedback (tenant_id, diagnosis_id, verdict,"
                " time_to_review_s) values (:t, :d, 'accepted', 600)",
            ):
                await connection.execute(
                    text(sql),
                    {
                        "t": tenant,
                        "s": f"piloto-{tenant[:8]}",
                        "g": integration,
                        "i": incident,
                        "d": diagnosis,
                        "k": f"piloto:{diagnosis}",
                        "at": now,
                    },
                )
        found = await pilot.measure(URL, tenant, now - timedelta(days=1), now + timedelta(days=1))
        assert found["mttr"] == pytest.approx(30)
        assert found["baseline"] == 120
        assert found["leaks"] == 0
        assert found["automatic"] == 0
        report = pilot.render(tenant, now, now, found, 80.0)
        assert "| Precisão de categoria | 100,0% |" in report
        assert "| Redução de MTTR | 75,0% |" in report
        assert "| Diagnósticos com Evidência rastreável | 0,0% |" in report
        assert "| SUS (usabilidade) | 80,0 |" in report
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("delete from doctor.tenants where id = :t"), {"t": tenant}
            )
            await connection.execute(
                text("delete from public.organizations where id = :t"), {"t": tenant}
            )
        await engine.dispose()
