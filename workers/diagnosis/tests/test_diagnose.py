"""Diagnóstico de ponta a ponta contra Postgres real (ticket #24): da Execução com erro ao
Diagnóstico publicado, com o FakeProvider no lugar do LLM."""

import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from aid_diagnosis_engine.llm.base import LLMUnavailableError
from aid_diagnosis_engine.llm.fake import FakeProvider
from aid_diagnosis_worker.diagnose import DbLoader, diagnose, open_automatic
from aid_diagnosis_worker.evaluate import evaluate_execution
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
T0 = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


async def rows(engine: AsyncEngine, sql: str, **params: Any) -> list[Any]:
    async with engine.begin() as connection:
        return list((await connection.execute(text(sql), params)).mappings())


async def incident_with_timeout(engine: AsyncEngine, ids: dict[str, str]) -> dict[str, str]:
    """Execução fechada com o 504 do PRD: as Regras abrem o Incidente (INT-003)."""
    execution, event = str(uuid4()), str(uuid4())
    await run(
        engine,
        "insert into doctor.executions (id, tenant_id, integration_id, status, first_event_at,"
        " last_event_at, event_count, closed_at) values (:x, :t, :i, 'failed', :at, :at, 1, now())",
        x=execution,
        t=ids["tenant"],
        i=ids["integration"],
        at=T0,
    )
    await run(
        engine,
        "insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version,"
        " source, operation, severity, dedup_key, error, execution_ref, correlated_by)"
        ' values (:id, :t, :i, :at, \'1.0\', \'{"provider": "sap", "service": "PI"}\','
        " 'BAPI_SALESORDER_CREATE', 'ERROR', :d, cast(:e as jsonb), :x, 'execution_id')",
        id=event,
        t=ids["tenant"],
        i=ids["integration"],
        at=T0,
        d=str(uuid4()),
        e=json.dumps({"category": "TIMEOUT", "http_status": 504, "message": "UPSTREAM_TIMEOUT"}),
        x=execution,
    )
    incident = await evaluate_execution(engine, {"execution_id": execution})
    assert incident is not None
    [match] = await rows(
        engine,
        "select id::text from doctor.rule_matches where execution_id = cast(:x as uuid)",
        x=execution,
    )
    return {"incident": incident, "event": event, "rule_match": match["id"]}


async def request(engine: AsyncEngine, ids: dict[str, str], incident: str, mode: str) -> str:
    diagnosis = str(uuid4())
    await run(
        engine,
        "insert into doctor.diagnoses (id, tenant_id, incident_id, version, requested_mode, mode,"
        " processing_key) values (:d, :t, :i, 1, :m, :m, :k)",
        d=diagnosis,
        t=ids["tenant"],
        i=incident,
        m=mode,
        k=f"teste:{diagnosis}",
    )
    return diagnosis


def answer(refs: list[str], **overrides: Any) -> str:
    body: dict[str, Any] = {
        "classification": "UPSTREAM_TIMEOUT",
        "status": "INCONCLUSIVE",
        "probable_cause": "O SAP não respondeu dentro do timeout do gateway.",
        "confidence": 0.68,
        "responsible_system": "indeterminado",
        "evidence": [{"ref": ref, "finding": "achado"} for ref in refs],
        "hypotheses": [{"statement": "Lentidão do SAP.", "confidence": 0.5}],
        "recommendations": [{"text": "Confira no SAP se o pedido existe.", "kind": "verify"}],
        "requires_human_review": True,
    }
    body.update(overrides)
    return json.dumps(body)


@pytest.mark.asyncio
async def test_exemplo_do_prd_e_tres_entregas_fazem_um_diagnostico(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    found = await incident_with_timeout(engine, tenant)
    diagnosis = await request(engine, tenant, found["incident"], "hybrid")
    provider = FakeProvider([answer([found["rule_match"], found["event"]])])

    results = [
        await diagnose(engine, {"diagnosis_id": diagnosis}, lambda name: provider) for _ in range(3)
    ]
    assert results == ["inconclusive", "ignored", "ignored"]
    [saved] = await rows(
        engine,
        "select status, stage, mode, classification, confidence::float, provider,"
        " duration_ms, published_at is not null as published, ruleset_version"
        " from doctor.diagnoses where id = cast(:d as uuid)",
        d=diagnosis,
    )
    assert dict(saved) == {
        "status": "inconclusive",
        "stage": "done",
        "mode": "hybrid",
        "classification": "UPSTREAM_TIMEOUT",
        "confidence": 0.68,
        "provider": "fake",
        "duration_ms": saved["duration_ms"],
        "published": True,
        "ruleset_version": "2026.10.1",
    }
    assert saved["duration_ms"] is not None
    evidence = await rows(
        engine,
        "select kind, coalesce(rule_match_id, event_id)::text as ref from doctor.diagnosis_evidence"
        " where diagnosis_id = cast(:d as uuid) order by rank",
        d=diagnosis,
    )
    assert [(e["kind"], e["ref"]) for e in evidence] == [
        ("rule_match", found["rule_match"]),
        ("event", found["event"]),
    ]
    published = await rows(
        engine,
        "select payload from doctor.outbox_messages where topic = 'diagnosis.published'"
        " and payload ->> 'diagnosis_id' = :d",
        d=diagnosis,
    )
    assert len(published) == 1


@pytest.mark.asyncio
async def test_evento_de_outra_organizacao_citado_pelo_llm_e_descartado(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    found = await incident_with_timeout(engine, tenant)
    other = {"tenant": str(uuid4()), "integration": str(uuid4())}
    await run(
        engine,
        "insert into public.organizations (id, name, slug) values (:t, 'B', :s)",
        t=other["tenant"],
        s=f"b-{other['tenant'][:30]}",
    )
    await run(engine, "insert into doctor.tenants (id) values (:t)", t=other["tenant"])
    await run(
        engine,
        "insert into doctor.integrations (id, tenant_id, name, source_system, target_system,"
        " environment) values (:i, :t, 'Notas SAP → GCP', 'sap', 'gcp', 'prd')",
        i=other["integration"],
        t=other["tenant"],
    )
    try:
        theirs = await incident_with_timeout(engine, other)
        # O worker lendo pelo tenant A não enxerga o Incidente de B.
        loader = DbLoader(engine, tenant["tenant"], theirs["incident"], FakeProvider())
        assert await loader.incident() is None

        diagnosis = await request(engine, tenant, found["incident"], "hybrid")
        provider = FakeProvider(
            [answer([theirs["event"], found["event"]], status="IDENTIFIED", confidence=0.8)]
        )
        assert await diagnose(engine, {"diagnosis_id": diagnosis}, lambda n: provider) == (
            "published"
        )
        [saved] = await rows(
            engine,
            "select verification_notes, confidence::float from doctor.diagnoses"
            " where id = cast(:d as uuid)",
            d=diagnosis,
        )
        assert (
            f"Evidência descartada: '{theirs['event']}' não pertence ao Incidente."
            in (saved["verification_notes"])
        )
        refs = await rows(
            engine,
            "select event_id::text from doctor.diagnosis_evidence"
            " where diagnosis_id = cast(:d as uuid)",
            d=diagnosis,
        )
        assert [r["event_id"] for r in refs] == [found["event"]]
        # O prompt também não levou nada de B.
        assert theirs["event"] not in provider.requests[0]["messages"][0].content
    finally:
        for table in (
            "incident_executions",
            "diagnoses",
            "incidents",
            "rule_matches",
            "events",
            "executions",
            "outbox_messages",
            "integrations",
        ):
            await run(engine, f"delete from doctor.{table} where tenant_id = :t", t=other["tenant"])  # noqa: S608
        await run(
            engine, "delete from doctor.incident_counters where tenant_id = :t", t=other["tenant"]
        )
        await run(engine, "delete from doctor.tenants where id = :t", t=other["tenant"])
        await run(engine, "delete from public.organizations where id = :t", t=other["tenant"])


@pytest.mark.asyncio
async def test_llm_fora_publica_com_as_regras_e_rules_only_nao_chama_o_llm(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    found = await incident_with_timeout(engine, tenant)
    failing = await request(engine, tenant, found["incident"], "hybrid")
    provider = FakeProvider([LLMUnavailableError("recusa")])
    assert await diagnose(engine, {"diagnosis_id": failing}, lambda n: provider) == "failed_llm"

    rules_only = str(uuid4())
    await run(
        engine,
        "insert into doctor.diagnoses (id, tenant_id, incident_id, version, requested_mode, mode,"
        " processing_key) values (:d, :t, :i, 2, 'rules_only', 'rules_only', :k)",
        d=rules_only,
        t=tenant["tenant"],
        i=found["incident"],
        k=f"teste:{rules_only}",
    )
    silent = FakeProvider()
    assert await diagnose(engine, {"diagnosis_id": rules_only}, lambda n: silent) == "published"
    assert silent.requests == []
    saved = await rows(
        engine,
        "select status, mode, (select count(*) from doctor.diagnosis_evidence e"
        " where e.diagnosis_id = d.id) as evidence from doctor.diagnoses d"
        " where d.incident_id = cast(:i as uuid) order by version",
        i=found["incident"],
    )
    assert [(r["status"], r["mode"], r["evidence"] > 0) for r in saved] == [
        ("failed_llm", "rules_only", True),
        ("published", "rules_only", True),
    ]


@pytest.mark.asyncio
async def test_falha_de_infraestrutura_devolve_a_fila(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    found = await incident_with_timeout(engine, tenant)
    diagnosis = await request(engine, tenant, found["incident"], "hybrid")

    def broken(name: str) -> FakeProvider:
        class Broken(FakeProvider):
            async def complete_structured(self, **kwargs: Any) -> Any:
                raise RuntimeError("rede")

        return Broken()

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await diagnose(engine, {"diagnosis_id": diagnosis}, broken)
        [saved] = await rows(
            engine,
            "select status, started_at from doctor.diagnoses where id = cast(:d as uuid)",
            d=diagnosis,
        )
        # Volta à fila na hora (sem esperar o prazo de posse) para a próxima entrega.
        assert (saved["status"], saved["started_at"]) == ("queued", None)
    # Na terceira, a falha que se repete vira `failed`, final como os outros.
    assert await diagnose(engine, {"diagnosis_id": diagnosis}, broken) == "failed"
    [saved] = await rows(
        engine,
        "select status, error, published_at is not null as published, attempts,"
        " (select count(*) from doctor.outbox_messages o where o.topic = 'diagnosis.published'"
        " and o.payload ->> 'diagnosis_id' = :d) as announced"
        " from doctor.diagnoses where id = cast(:d as uuid)",
        d=diagnosis,
    )
    assert dict(saved) == {
        "status": "failed",
        "error": "Erro interno ao gerar o Diagnóstico.",
        "published": True,
        "attempts": 3,
        "announced": 1,
    }


@pytest.mark.asyncio
async def test_automatico_so_com_a_opcao_ligada_e_incidente_critico(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    found = await incident_with_timeout(engine, tenant)
    payload = {"incident_id": found["incident"]}
    await run(
        engine,
        "update doctor.incidents set severity = 'critical' where id = cast(:i as uuid)",
        i=found["incident"],
    )
    assert await open_automatic(engine, payload) is None
    await run(
        engine,
        "update doctor.tenants set auto_diagnose_critical = true where id = cast(:t as uuid)",
        t=tenant["tenant"],
    )
    created = await open_automatic(engine, payload)
    assert created is not None
    assert await open_automatic(engine, payload) is None
    queued = await rows(
        engine,
        "select count(*) as n from doctor.outbox_messages where topic = 'diagnosis.requested'"
        " and payload ->> 'diagnosis_id' = :d",
        d=created,
    )
    assert queued[0]["n"] == 1


@pytest.mark.asyncio
async def test_base_sem_embedding_segue_pelo_texto(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    from aid_diagnosis_engine.llm.base import LLMTransientError

    class NoEmbedding(FakeProvider):
        async def embed(self, texts: Any, *, input_type: Any) -> list[list[float]]:
            raise LLMTransientError("429")

    found = await incident_with_timeout(engine, tenant)
    loader = DbLoader(engine, tenant["tenant"], found["incident"], NoEmbedding())
    # Sem exceção: busca só por texto (a Base global pode estar vazia neste banco).
    assert isinstance(list(await loader.knowledge("timeout 504 gateway")), list)
