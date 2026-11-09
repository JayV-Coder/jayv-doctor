"""Geração do Relatório técnico contra Postgres real (ticket #32): o arquivo, o hash e o prazo de
10 s para um Incidente com 100 Execuções."""

import hashlib
import json
import os
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from aid_diagnosis_engine.llm.fake import FakeProvider
from aid_diagnosis_worker.diagnose import diagnose
from aid_diagnosis_worker.evaluate import evaluate_execution
from aid_diagnosis_worker.report import ReportBusyError, generate_report
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")
AT = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=2)
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")


class MemoryStorage:
    def __init__(self, fail: int = 0) -> None:
        self.files: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.fail = fail

    async def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        if self.fail:
            self.fail -= 1
            raise ConnectionError("Storage fora do ar")
        self.files[(bucket, path)] = (data, content_type)

    async def remove(self, bucket: str, paths: Sequence[str]) -> None:
        for path in paths:
            self.files.pop((bucket, path), None)


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


async def one(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.begin() as connection:
        return (await connection.execute(text(sql), params)).mappings().first()


async def incident_with(engine: AsyncEngine, ids: dict[str, str], executions: int) -> str:
    """Execuções fechadas com um 504 cada: as Regras agrupam todas num Incidente (INT-003)."""
    await run(engine, "select doctor.ensure_event_partition(:d)", d=AT.date())
    found = None
    for n in range(executions):
        execution = str(uuid4())
        at = AT + timedelta(seconds=n)
        await run(
            engine,
            "insert into doctor.executions (id, tenant_id, integration_id, status,"
            " first_event_at, last_event_at, event_count, closed_at)"
            " values (:x, :t, :i, 'failed', :at, :at, 1, now())",
            at=at,
            x=execution,
            t=ids["tenant"],
            i=ids["integration"],
        )
        await run(
            engine,
            "insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version,"
            " source, operation, severity, dedup_key, error, execution_ref, correlated_by,"
            " business_reference) values (:id, :t, :i, :at, '1.0', '{}', 'BAPI', 'ERROR', :d,"
            " cast(:e as jsonb), :x, 'execution_id', :ref)",
            at=at,
            id=str(uuid4()),
            t=ids["tenant"],
            i=ids["integration"],
            d=str(uuid4()),
            e=json.dumps({"http_status": 504, "message": "UPSTREAM_TIMEOUT"}),
            x=execution,
            ref="hmac:" + "e" * 64,
        )
        found = await evaluate_execution(engine, {"execution_id": execution})
    assert found is not None
    return found


async def diagnosed(engine: AsyncEngine, ids: dict[str, str], incident: str) -> str:
    diagnosis = str(uuid4())
    await run(
        engine,
        "insert into doctor.diagnoses (id, tenant_id, incident_id, version, requested_mode, mode,"
        " processing_key) values (:d, :t, :i, 1, 'rules_only', 'rules_only', :k)",
        d=diagnosis,
        t=ids["tenant"],
        i=incident,
        k=f"teste:{diagnosis}",
    )
    provider = FakeProvider()
    assert await diagnose(engine, {"diagnosis_id": diagnosis}, lambda n: provider) in (
        "published",
        "inconclusive",
    )
    return diagnosis


async def requested(engine: AsyncEngine, ids: dict[str, str], incident: str, **options: Any) -> str:
    report = str(uuid4())
    await run(
        engine,
        "insert into doctor.reports (id, tenant_id, incident_id, diagnosis_id, format,"
        " include_timeline, include_event_excerpts, processing_key)"
        " select :r, :t, :i, (select id from doctor.diagnoses where incident_id = :i"
        " order by version desc limit 1), :f, :tl, :ex, :k",
        r=report,
        t=ids["tenant"],
        i=incident,
        f=options.get("format", "md"),
        tl=options.get("timeline", False),
        ex=options.get("excerpts", False),
        k=f"teste:{report}",
    )
    return report


@pytest.mark.asyncio
async def test_relatorio_vai_para_o_storage_com_o_hash_e_sem_referencia_em_claro(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    incident = await incident_with(engine, tenant, 2)
    await diagnosed(engine, tenant, incident)
    report = await requested(engine, tenant, incident, timeline=True, excerpts=True)
    storage = MemoryStorage()

    assert await generate_report(engine, {"report_id": report}, storage) == "ready"
    row = await one(
        engine,
        "select status, storage_path, size_bytes, content_sha256 from doctor.reports where id = :r",
        r=report,
    )
    assert row["status"] == "ready"
    assert row["storage_path"] == f"{tenant['tenant']}/{report}.md"
    content, content_type = storage.files[("doctor-reports", row["storage_path"])]
    assert content_type == "text/markdown"
    assert row["size_bytes"] == len(content)
    body = content.decode()
    assert hashlib.sha256(content).hexdigest() == row["content_sha256"]
    text_part, footer = body.rsplit("\n---\n", 1)
    assert hashlib.sha256(text_part.encode() + b"\n").hexdigest() in footer
    assert "## Timeline" in body
    assert "UPSTREAM_TIMEOUT" in body
    assert "hmac:" not in body
    audit = await one(
        engine,
        "select count(*) as n from doctor.audit_logs where tenant_id = :t"
        " and action = 'report.generated' and resource_id = :r",
        t=tenant["tenant"],
        r=report,
    )
    assert audit["n"] == 1
    # Entrega repetida não gera de novo.
    assert await generate_report(engine, {"report_id": report}, storage) == "ignored"


@pytest.mark.asyncio
async def test_pdf_de_incidente_com_100_execucoes_em_menos_de_10_s(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    incident = await incident_with(engine, tenant, 100)
    await diagnosed(engine, tenant, incident)
    report = await requested(engine, tenant, incident, format="pdf", timeline=True, excerpts=True)
    storage = MemoryStorage()

    started = time.perf_counter()
    assert await generate_report(engine, {"report_id": report}, storage) == "ready"
    assert time.perf_counter() - started < 10
    content, content_type = storage.files[("doctor-reports", f"{tenant['tenant']}/{report}.pdf")]
    assert content.startswith(b"%PDF")
    assert content_type == "application/pdf"


@pytest.mark.asyncio
async def test_storage_fora_do_ar_volta_para_a_fila_e_desiste_na_terceira(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    incident = await incident_with(engine, tenant, 1)
    report = await requested(engine, tenant, incident)
    storage = MemoryStorage(fail=3)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            await generate_report(engine, {"report_id": report}, storage)
        row = await one(engine, "select status from doctor.reports where id = :r", r=report)
        assert row["status"] == "queued"
    assert await generate_report(engine, {"report_id": report}, storage) == "failed"
    row = await one(engine, "select status, error from doctor.reports where id = :r", r=report)
    assert (row["status"], row["error"]) == ("failed", "Não foi possível gerar o relatório.")


@pytest.mark.asyncio
async def test_entrega_repetida_durante_a_geracao_volta_para_a_fila(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    incident = await incident_with(engine, tenant, 1)
    report = await requested(engine, tenant, incident)
    await run(engine, "update doctor.reports set status = 'running' where id = :r", r=report)
    with pytest.raises(ReportBusyError):
        await generate_report(engine, {"report_id": report}, MemoryStorage())
    # Posse vencida (o worker caiu no meio): a próxima entrega retoma.
    async with engine.begin() as connection:
        # Sem o trigger de updated_at, para simular o relógio.
        await connection.execute(text("set local session_replication_role = replica"))
        await connection.execute(
            text(
                "update doctor.reports set updated_at = now() - interval '3 minutes' where id = :r"
            ),
            {"r": report},
        )
    assert await generate_report(engine, {"report_id": report}, MemoryStorage()) == "ready"
