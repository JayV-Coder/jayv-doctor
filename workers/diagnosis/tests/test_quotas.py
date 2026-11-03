"""Cotas contra Postgres real (ticket #31): contadores sob concorrência, o Diagnóstico sem Cota
de IA e o aviso por e-mail."""

import asyncio
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from aid_db import platform_role
from aid_diagnosis_engine.llm.fake import FakeProvider
from aid_diagnosis_worker.diagnose import diagnose
from aid_diagnosis_worker.evaluate import evaluate_execution
from aid_diagnosis_worker.notify import notify_threshold
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")
AT = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=30)
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


async def scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.begin() as connection:
        return await connection.scalar(text(sql), params)


@pytest.mark.asyncio
async def test_50_workers_em_paralelo_nao_perdem_incremento(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    async def worker() -> None:
        for _ in range(4):
            async with engine.begin() as connection:
                await platform_role(connection)
                await connection.execute(
                    text("select doctor.increment_usage(cast(:t as uuid), 'diagnoses_llm', 1)"),
                    {"t": tenant["tenant"]},
                )

    await asyncio.gather(*(worker() for _ in range(50)))
    used = await scalar(
        engine,
        "select doctor.current_usage(cast(:t as uuid), 'diagnoses_llm')",
        t=tenant["tenant"],
    )
    assert used == 200


async def incident(engine: AsyncEngine, ids: dict[str, str]) -> str:
    """Execução fechada com um 504: as Regras abrem o Incidente (INT-003)."""
    execution = str(uuid4())
    await run(
        engine,
        "insert into doctor.executions (id, tenant_id, integration_id, status, first_event_at,"
        " last_event_at, event_count, closed_at) values (:x, :t, :i, 'failed', :at, :at, 1,"
        " now())",
        at=AT,
        x=execution,
        t=ids["tenant"],
        i=ids["integration"],
    )
    await run(
        engine,
        "insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version,"
        " source, operation, severity, dedup_key, error, execution_ref, correlated_by)"
        " values (:id, :t, :i, :at, '1.0', '{}', 'BAPI', 'ERROR', :d, cast(:e as jsonb), :x,"
        " 'execution_id')",
        at=AT,
        id=str(uuid4()),
        t=ids["tenant"],
        i=ids["integration"],
        d=str(uuid4()),
        e=json.dumps({"http_status": 504, "message": "UPSTREAM_TIMEOUT"}),
        x=execution,
    )
    found = await evaluate_execution(engine, {"execution_id": execution})
    assert found is not None
    return found


@pytest.mark.asyncio
async def test_sem_cota_de_ia_o_diagnostico_roda_so_com_regras(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    await run(
        engine,
        "select doctor.ensure_event_partition(now()::date)",
    )
    target = await incident(engine, tenant)
    await run(
        engine,
        "insert into doctor.usage_records (tenant_id, resource, period_start, quantity) values"
        " (:t, 'diagnoses_llm', doctor.usage_period('diagnoses_llm'), 1000)",
        t=tenant["tenant"],
    )
    diagnosis = str(uuid4())
    await run(
        engine,
        "insert into doctor.diagnoses (id, tenant_id, incident_id, version, requested_mode, mode,"
        " processing_key) values (:d, :t, :i, 1, 'hybrid', 'hybrid', :k)",
        d=diagnosis,
        t=tenant["tenant"],
        i=target,
        k=f"cota:{diagnosis}",
    )
    provider = FakeProvider()
    assert await diagnose(engine, {"diagnosis_id": diagnosis}, lambda n: provider) == "published"
    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    "select mode, verification_notes from doctor.diagnoses"
                    " where id = cast(:d as uuid)"
                ),
                {"d": diagnosis},
            )
        ).one()
    assert row.mode == "rules_only"
    assert row.verification_notes[0] == "Cota de IA do mês esgotada: Diagnóstico só com as Regras."
    assert provider.requests == []


@pytest.mark.asyncio
async def test_diagnostico_com_llm_registra_tokens_e_consome_a_cota(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    await run(engine, "select doctor.ensure_event_partition(now()::date)")
    target = await incident(engine, tenant)
    diagnosis = str(uuid4())
    await run(
        engine,
        "insert into doctor.diagnoses (id, tenant_id, incident_id, version, requested_mode, mode,"
        " processing_key) values (:d, :t, :i, 1, 'hybrid', 'hybrid', :k)",
        d=diagnosis,
        t=tenant["tenant"],
        i=target,
        k=f"cota:{diagnosis}",
    )
    answer = {
        "classification": "TIMEOUT",
        "status": "INCONCLUSIVE",
        "probable_cause": "Timeout.",
        "confidence": 0.5,
        "responsible_system": "indeterminado",
        "evidence": [],
        "hypotheses": [],
        "recommendations": [],
        "requires_human_review": True,
    }
    provider = FakeProvider([json.dumps(answer)])
    await diagnose(engine, {"diagnosis_id": diagnosis}, lambda n: provider)
    async with engine.begin() as connection:
        usage = (
            await connection.execute(
                text(
                    "select provider, input_tokens > 0 as billed from doctor.usage_llm"
                    " where diagnosis_id = cast(:d as uuid)"
                ),
                {"d": diagnosis},
            )
        ).one()
        used = await connection.scalar(
            text("select doctor.current_usage(cast(:t as uuid), 'diagnoses_llm')"),
            {"t": tenant["tenant"]},
        )
    assert (usage.provider, usage.billed, used) == ("fake", True, 1)


class Mail:
    def __init__(self) -> None:
        self.sent: list[tuple[Sequence[str], str, str]] = []

    def send(self, to: Sequence[str], subject: str, body: str) -> None:
        self.sent.append((list(to), subject, body))


@pytest.mark.asyncio
async def test_aviso_de_cota_vai_para_owner_e_admin(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    owner = str(uuid4())
    await run(
        engine,
        "insert into auth.users (id, instance_id, aud, role, email) values (:u,"
        " '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :e)",
        u=owner,
        e=f"{owner}@cota.test",
    )
    await run(
        engine,
        "insert into public.organization_members (org_id, user_id, role) values (:t, :u, 'member')",
        t=tenant["tenant"],
        u=owner,
    )
    await run(
        engine,
        "insert into doctor.memberships (tenant_id, user_id, role) values (:t, :u, 'owner')",
        t=tenant["tenant"],
        u=owner,
    )
    try:
        mail = Mail()
        payload = {"tenant_id": tenant["tenant"], "resource": "diagnoses_llm", "threshold": 100}
        assert await notify_threshold(engine, payload, mail) == 1
        [(to, subject, body)] = mail.sent
        assert to == [f"{owner}@cota.test"]
        assert "Cota de diagnósticos com ia no mês atingida" in subject
        assert "só com as Regras" in body
    finally:
        await run(engine, "delete from doctor.memberships where user_id = :u", u=owner)
        await run(engine, "delete from public.organization_members where user_id = :u", u=owner)
        await run(engine, "delete from auth.users where id = :u", u=owner)
