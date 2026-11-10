"""Regras e Incidentes contra Postgres real. Roda com INTEGRATION_DB_URL (job de E2E do CI)."""

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from aid_correlation_worker.close import close_idle
from aid_correlation_worker.correlate import correlate_integration
from aid_diagnosis_engine.rules import RULES, RULESET_VERSION
from aid_diagnosis_engine.rules import catalog as catalog_module
from aid_diagnosis_worker.evaluate import evaluate_execution
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
T0 = datetime(2026, 11, 2, 14, 0, tzinfo=UTC)
TIMEOUT_504 = {"category": "UNKNOWN", "http_status": 504, "message": "UPSTREAM_TIMEOUT"}


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


async def rows(engine: AsyncEngine, sql: str, **params: Any) -> list[Any]:
    async with engine.begin() as connection:
        return list((await connection.execute(text(sql), params)).mappings())


async def closed_execution(
    engine: AsyncEngine, ids: dict[str, str], at: datetime, error: dict[str, Any] | None
) -> str:
    """Execução fechada com um Evento (o que o worker de correlação deixaria pronto)."""
    execution = str(uuid4())
    await run(
        engine,
        "insert into doctor.executions (id, tenant_id, integration_id, status, first_event_at,"
        " last_event_at, event_count, closed_at) values (:x, :t, :i, :s, :at, :at, 1, now())",
        x=execution,
        t=ids["tenant"],
        i=ids["integration"],
        s="failed" if error else "success",
        at=at,
    )
    await run(
        engine,
        "insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version,"
        " source, operation, severity, dedup_key, error, execution_ref, correlated_by)"
        ' values (:id, :t, :i, :at, \'1.0\', \'{"provider": "sap", "service": "PI"}\', \'BAPI\','
        " :sev, :d, cast(:e as jsonb), :x, 'execution_id')",
        id=str(uuid4()),
        t=ids["tenant"],
        i=ids["integration"],
        at=at,
        sev="ERROR" if error else "INFO",
        d=str(uuid4()),
        e=json.dumps(error) if error else None,
        x=execution,
    )
    return execution


async def incidents(engine: AsyncEngine, ids: dict[str, str]) -> list[Any]:
    return await rows(
        engine,
        "select id::text, category, severity, execution_count, title, rule_code, rule_version,"
        " first_seen_at, last_seen_at from doctor.incidents where tenant_id = :t"
        " order by first_seen_at",
        t=ids["tenant"],
    )


@pytest.mark.asyncio
async def test_37_execucoes_com_504_em_18_min_abrem_um_incidente_critico(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    for index in range(37):
        execution = await closed_execution(
            engine, tenant, T0 + timedelta(seconds=index * 29), TIMEOUT_504
        )
        await evaluate_execution(engine, {"execution_id": execution})
    (incident,) = await incidents(engine, tenant)
    assert incident["category"] == "TIMEOUT"
    assert incident["severity"] == "critical"
    assert incident["execution_count"] == 37
    assert incident["title"] == "Timeout · Pedidos SF → SAP"
    topics = await rows(
        engine,
        "select topic, count(*) as n from doctor.outbox_messages where tenant_id = :t"
        " group by topic order by topic",
        t=tenant["tenant"],
    )
    # Sem Regra de alerta na Organização, nenhuma `alert.evaluate` a mais na outbox (#41).
    assert [(t["topic"], t["n"]) for t in topics] == [
        ("incident.opened", 1),
        ("incident.updated", 36),
    ]


@pytest.mark.asyncio
async def test_fora_da_janela_de_30_min_abre_outro_incidente(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    for at in (T0, T0 + timedelta(minutes=20), T0 + timedelta(hours=2)):
        execution = await closed_execution(engine, tenant, at, TIMEOUT_504)
        await evaluate_execution(engine, {"execution_id": execution})
    assert [i["execution_count"] for i in await incidents(engine, tenant)] == [2, 1]


@pytest.mark.asyncio
async def test_mensagem_repetida_nao_duplica(engine: AsyncEngine, tenant: dict[str, str]) -> None:
    execution = await closed_execution(engine, tenant, T0, {"category": "AUTH", "http_status": 401})
    for _ in range(2):
        await evaluate_execution(engine, {"execution_id": execution})
    (incident,) = await incidents(engine, tenant)
    assert incident["execution_count"] == 1
    # Regra de severidade alta em produção: sobe para crítica.
    assert incident["severity"] == "critical"
    matches = await rows(
        engine, "select rule_code from doctor.rule_matches where tenant_id = :t", t=tenant["tenant"]
    )
    assert [m["rule_code"] for m in matches] == ["INT-001"]


@pytest.mark.asyncio
async def test_sem_match_nao_abre_incidente(engine: AsyncEngine, tenant: dict[str, str]) -> None:
    execution = await closed_execution(engine, tenant, T0, None)
    assert await evaluate_execution(engine, {"execution_id": execution}) is None
    assert await incidents(engine, tenant) == []


@pytest.mark.asyncio
async def test_versao_nova_da_regra_nao_mexe_nos_matches_antigos(
    engine: AsyncEngine, tenant: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    old = await closed_execution(engine, tenant, T0, TIMEOUT_504)
    await evaluate_execution(engine, {"execution_id": old})
    await run(
        engine,
        "insert into doctor.rule_definitions (code, version, category, severity_hint, description)"
        " values ('INT-003', '2099.1.0', 'TIMEOUT', 'high', 'teste') on conflict do nothing",
    )
    try:
        newer = tuple(
            type(item)(**{**item.__dict__, "version": "2099.1.0"}) for item in catalog_module.RULES
        )
        monkeypatch.setattr("aid_diagnosis_engine.rules.RULES", newer[2:3])
        new = await closed_execution(engine, tenant, T0 + timedelta(minutes=1), TIMEOUT_504)
        await evaluate_execution(engine, {"execution_id": new})
        found = await rows(
            engine,
            "select execution_id::text as x, rule_version from doctor.rule_matches"
            " where tenant_id = :t",
            t=tenant["tenant"],
        )
        assert {(f["x"], f["rule_version"]) for f in found} == {
            (old, RULESET_VERSION),
            (new, "2099.1.0"),
        }
    finally:
        await run(
            engine, "delete from doctor.rule_matches where tenant_id = :t", t=tenant["tenant"]
        )
        await run(
            engine,
            "delete from doctor.incident_executions where tenant_id = :t",
            t=tenant["tenant"],
        )
        await run(engine, "delete from doctor.incidents where tenant_id = :t", t=tenant["tenant"])
        await run(engine, "delete from doctor.rule_definitions where version = '2099.1.0'")


@pytest.mark.asyncio
async def test_catalogo_do_banco_e_o_do_codigo(engine: AsyncEngine) -> None:
    stored = await rows(
        engine,
        "select code, version, category, severity_hint, description"
        " from doctor.rule_definitions where version = :v order by code",
        v=RULESET_VERSION,
    )
    assert [tuple(row.values()) for row in stored] == [
        (r.code, r.version, r.category, r.severity_hint, r.description_pt) for r in RULES
    ]


@pytest.mark.asyncio
async def test_de_ponta_a_ponta_eventos_execucao_incidente(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    for offset, error in ((0, None), (1, TIMEOUT_504)):
        await run(
            engine,
            "insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version,"
            " source, operation, severity, dedup_key, execution_id, error) values (:id, :t, :i,"
            ' :at, \'1.0\', \'{"provider": "sap", "service": "PI"}\', \'BAPI\', :sev, :d,'
            " 'exec-123', cast(:e as jsonb))",
            id=str(uuid4()),
            t=tenant["tenant"],
            i=tenant["integration"],
            at=T0 + timedelta(seconds=offset * 30),
            sev="ERROR" if error else "INFO",
            d=str(uuid4()),
            e=json.dumps(error) if error else None,
        )
    await correlate_integration(engine, {"integration_id": tenant["integration"]})
    await run(
        engine,
        "update doctor.executions set last_activity_at = now() - interval '6 minutes'"
        " where tenant_id = :t",
        t=tenant["tenant"],
    )
    await close_idle(engine)
    (queued,) = await rows(
        engine,
        "select payload from doctor.outbox_messages where tenant_id = :t"
        " and topic = 'rules.evaluate'",
        t=tenant["tenant"],
    )
    await evaluate_execution(engine, queued["payload"])
    (incident,) = await incidents(engine, tenant)
    assert (incident["category"], incident["execution_count"]) == ("TIMEOUT", 1)


async def add_event(
    engine: AsyncEngine, ids: dict[str, str], execution: str, at: datetime, **fields: Any
) -> None:
    await run(
        engine,
        "insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version,"
        " source, operation, severity, dedup_key, error, attributes, execution_ref)"
        ' values (:id, :t, :i, :at, \'1.0\', \'{"provider": "sap", "service": "PI"}\', \'BAPI\','
        " :sev, :d, cast(:e as jsonb), cast(:a as jsonb), :x)",
        id=str(uuid4()),
        t=ids["tenant"],
        i=ids["integration"],
        at=at,
        sev=fields.get("severity", "INFO"),
        d=str(uuid4()),
        e=json.dumps(fields["error"]) if "error" in fields else None,
        a=json.dumps(fields.get("attributes", {})),
        x=execution,
    )
    await run(
        engine,
        "update doctor.executions set last_event_at = greatest(last_event_at, :at),"
        " closed_at = now() where id = :x",
        at=at,
        x=execution,
    )


@pytest.mark.asyncio
async def test_reavaliacao_move_a_execucao_para_o_incidente_certo(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    execution = await closed_execution(engine, tenant, T0, None)
    await run(
        engine,
        'update doctor.events set attributes = \'{"confirmation": "pending"}\''
        " where execution_ref = :x",
        x=execution,
    )
    first = await evaluate_execution(engine, {"execution_id": execution})
    assert first is not None
    # A confirmação chega tarde, junto com um 401: reabre, fecha e é avaliada de novo.
    await add_event(
        engine,
        tenant,
        execution,
        T0 + timedelta(minutes=7),
        severity="ERROR",
        error={"category": "AUTH", "http_status": 401},
        attributes={"confirmation": "received"},
    )
    second = await evaluate_execution(engine, {"execution_id": execution})
    found = {i["category"]: i["execution_count"] for i in await incidents(engine, tenant)}
    assert found == {"PENDING_CONFIRMATION": 0, "AUTH": 1}
    assert second != first
    codes = await rows(
        engine,
        "select rule_code from doctor.rule_matches where execution_id = :x order by rule_code",
        x=execution,
    )
    assert [c["rule_code"] for c in codes] == ["INT-001"]


@pytest.mark.asyncio
async def test_execucao_aberta_ou_fundida_nao_e_avaliada(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    execution = await closed_execution(engine, tenant, T0, TIMEOUT_504)
    await run(engine, "update doctor.executions set closed_at = null where id = :x", x=execution)
    assert await evaluate_execution(engine, {"execution_id": execution}) is None
    assert await incidents(engine, tenant) == []


@pytest.mark.asyncio
async def test_fusao_nao_conta_a_mesma_execucao_duas_vezes(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    absorbed = await closed_execution(engine, tenant, T0, TIMEOUT_504)
    incident = await evaluate_execution(engine, {"execution_id": absorbed})
    survivor = await closed_execution(engine, tenant, T0 - timedelta(seconds=5), None)
    await run(
        engine,
        "update doctor.events set execution_ref = :s where execution_ref = :a",
        s=survivor,
        a=absorbed,
    )
    await run(
        engine,
        "update doctor.executions set merged_into = :s, event_count = 0 where id = :a",
        s=survivor,
        a=absorbed,
    )
    await run(
        engine,
        "update doctor.executions set last_event_at = :at, status = 'failed' where id = :s",
        s=survivor,
        at=T0,
    )
    assert await evaluate_execution(engine, {"execution_id": survivor}) == incident
    (only,) = await incidents(engine, tenant)
    assert only["execution_count"] == 1
    linked = await rows(
        engine,
        "select execution_id::text as x from doctor.incident_executions where tenant_id = :t",
        t=tenant["tenant"],
    )
    assert [link["x"] for link in linked] == [survivor]


@pytest.mark.asyncio
async def test_incidente_resolvido_reabre_com_a_mesma_assinatura_em_24_h(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    first = await closed_execution(engine, tenant, T0, TIMEOUT_504)
    incident = await evaluate_execution(engine, {"execution_id": first})
    await run(
        engine,
        "update doctor.incidents set status = 'resolved', resolution_note = 'Gateway ajustado.'"
        " where id = :i",
        i=incident,
    )
    # Bem depois da janela de 30 min, mas dentro de 24 h da resolução: reabre o mesmo.
    await run(
        engine,
        "update doctor.incidents set resolved_at = :r where id = :i",
        r=T0 + timedelta(hours=1),
        i=incident,
    )
    later = await closed_execution(engine, tenant, T0 + timedelta(hours=3), TIMEOUT_504)
    assert await evaluate_execution(engine, {"execution_id": later}) == incident
    (only,) = await incidents(engine, tenant)
    assert only["execution_count"] == 2
    history = await rows(
        engine,
        "select action, from_value, to_value, actor_id from doctor.incident_history"
        " where incident_id = :i",
        i=incident,
    )
    assert [(h["action"], h["from_value"], h["to_value"], h["actor_id"]) for h in history] == [
        ("reopened", "resolved", "open", None)
    ]


@pytest.mark.asyncio
async def test_reavaliar_execucao_de_incidente_resolvido_nao_reabre(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    execution = await closed_execution(engine, tenant, T0, TIMEOUT_504)
    incident = await evaluate_execution(engine, {"execution_id": execution})
    await run(
        engine,
        "update doctor.incidents set status = 'resolved', resolution_note = 'ok' where id = :i",
        i=incident,
    )
    assert await evaluate_execution(engine, {"execution_id": execution}) == incident
    # Execução de antes da resolução (Importação atrasada) também não reabre: abre outro.
    old = await closed_execution(engine, tenant, T0 - timedelta(hours=10), TIMEOUT_504)
    assert await evaluate_execution(engine, {"execution_id": old}) != incident
    statuses = await rows(engine, "select status from doctor.incidents where id = :i", i=incident)
    assert statuses[0]["status"] == "resolved"


@pytest.mark.asyncio
async def test_indexa_documento_e_reindexa_quando_o_modelo_muda(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    from aid_diagnosis_engine.llm.fake import FakeProvider
    from aid_diagnosis_worker.knowledge import index, reindex_stale

    document = str(uuid4())
    await run(
        engine,
        "insert into doctor.knowledge_documents (id, tenant_id, title, source, storage_path,"
        " content_type, size_bytes, status) values (:d, :t, 'Runbook', 'upload', :p,"
        " 'text/markdown', 40, 'indexing')",
        d=document,
        t=tenant["tenant"],
        p=f"{tenant['tenant']}/{document}/runbook.md",
    )

    class Store:
        async def read(self, path: str) -> bytes | None:
            return b"# Runbook\n\nCliente CPF 529.982.247-25 com o job VL10 travado."

    provider = FakeProvider()
    assert (
        await index(engine, {"document_id": document}, Store(), lambda name, project: provider)
        == "ready"
    )
    stored = await rows(
        engine,
        "select d.status, d.chunk_count, d.embedding_model, c.content from"
        " doctor.knowledge_documents d join doctor.knowledge_chunks c on c.document_id = d.id"
        " where d.id = :d",
        d=document,
    )
    assert (stored[0]["status"], stored[0]["chunk_count"], stored[0]["embedding_model"]) == (
        "ready",
        1,
        "fake",
    )
    # A Sanitização roda antes do embedding: o CPF não vira Fragmento.
    assert "529.982.247-25" not in stored[0]["content"]
    # O provedor da Organização é `anthropic`, cujo modelo não é `fake`: volta para a fila.
    from aid_diagnosis_engine.llm.registry import provider_for

    assert await reindex_stale(engine, provider_for) >= 1
    queued = await rows(
        engine,
        "select d.status, d.reindex_queued_at is not null as queued,"
        " (select count(*) from doctor.outbox_messages o where o.topic = 'knowledge.index'"
        " and o.payload ->> 'document_id' = :d) as messages"
        " from doctor.knowledge_documents d where d.id = cast(:d as uuid)",
        d=document,
    )
    # Segue `ready` (achável pelo texto) até reindexar; o pedido não se repete na hora seguinte.
    assert (queued[0]["status"], queued[0]["queued"], queued[0]["messages"]) == ("ready", True, 1)
    await reindex_stale(engine, provider_for)
    again = await rows(
        engine,
        "select count(*) as n from doctor.outbox_messages where topic = 'knowledge.index'"
        " and payload ->> 'document_id' = :d",
        d=document,
    )
    assert again[0]["n"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "failure", "status"),
    [
        (b"%PDF-1.4 corrompido", None, "failed"),
        (b"# Doc\n\ntexto", "unavailable", "failed"),
        (b"# Doc\n\ntexto", "transient", "indexing"),
    ],
)
async def test_falha_definitiva_marca_o_documento_e_passageira_reentrega(
    engine: AsyncEngine, tenant: dict[str, str], data: bytes, failure: str | None, status: str
) -> None:
    from aid_diagnosis_engine.llm.base import LLMTransientError, LLMUnavailableError
    from aid_diagnosis_engine.llm.fake import FakeProvider
    from aid_diagnosis_worker.knowledge import index

    document = str(uuid4())
    kind = "application/pdf" if data.startswith(b"%PDF") else "text/markdown"
    await run(
        engine,
        "insert into doctor.knowledge_documents (id, tenant_id, title, source, storage_path,"
        " content_type, size_bytes, status) values (:d, :t, 'Doc', 'upload', :p, :c, 40,"
        " 'indexing')",
        d=document,
        t=tenant["tenant"],
        p=f"{tenant['tenant']}/{document}/document.md",
        c=kind,
    )

    class Store:
        async def read(self, path: str) -> bytes | None:
            return data

    class Provider(FakeProvider):
        async def embed(self, texts: Any, *, input_type: Any) -> list[list[float]]:
            if failure == "transient":
                raise LLMTransientError("429")
            raise LLMUnavailableError("chave inválida")

    provider = Provider() if failure else FakeProvider()
    if failure == "transient":
        with pytest.raises(LLMTransientError):
            await index(engine, {"document_id": document}, Store(), lambda name, project: provider)
    else:
        assert await index(
            engine, {"document_id": document}, Store(), lambda n, _project: provider
        ) == ("failed")
    found = await rows(
        engine, "select status, error from doctor.knowledge_documents where id = :d", d=document
    )
    assert found[0]["status"] == status
    assert (found[0]["error"] is None) == (status == "indexing")


@pytest.mark.asyncio
async def test_bapiret2_v1_abre_incidente_por_int_005_com_a_mensagem_sap(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    """Critério do #38: o Evento passa pela ingestão de verdade (EventSanitizer), que reconhece o
    RETURN da BAPI, e a Regra classifica com o Evento como Evidência."""
    from aid_ingestion.cleaning import EventSanitizer

    body = json.dumps(
        {
            "RETURN": [
                {
                    "TYPE": "E",
                    "ID": "V1",
                    "NUMBER": "801",
                    "MESSAGE": "Pedido bloqueado para faturamento",
                }
            ]
        }
    )
    cleaned, _ = EventSanitizer(b"k" * 32, tenant["tenant"])(
        {
            "schema_version": "1.0",
            "event_id": str(uuid4()),
            "integration_id": tenant["integration"],
            "timestamp": T0.isoformat(),
            "source": {"provider": "sap", "service": "ECC"},
            "operation": "BAPI_SALESORDER_CREATEFROMDAT2",
            "severity": "INFO",
            "attributes": {"response": body},
        }
    )
    execution, event = str(uuid4()), str(uuid4())
    await run(
        engine,
        "insert into doctor.executions (id, tenant_id, integration_id, status, first_event_at,"
        " last_event_at, event_count, closed_at) values (:x, :t, :i, 'failed', :at, :at, 1, now())",
        x=execution,
        t=tenant["tenant"],
        i=tenant["integration"],
        at=T0,
    )
    await run(
        engine,
        "insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version,"
        " source, operation, severity, dedup_key, error, attributes, execution_ref, correlated_by)"
        " values (:id, :t, :i, :at, '1.0', cast(:src as jsonb), :op, :sev, :d, cast(:e as jsonb),"
        " cast(:a as jsonb), :x, 'execution_id')",
        id=event,
        t=tenant["tenant"],
        i=tenant["integration"],
        at=T0,
        src=json.dumps(cleaned["source"]),
        op=cleaned["operation"],
        sev=cleaned["severity"],
        d=str(uuid4()),
        e=json.dumps(cleaned["error"]),
        a=json.dumps(cleaned["attributes"]),
        x=execution,
    )
    await evaluate_execution(engine, {"execution_id": execution})
    opened = await incidents(engine, tenant)
    assert [(i["rule_code"], i["category"]) for i in opened] == [("INT-005", "BUSINESS_REJECTION")]
    match = await rows(
        engine,
        "select matched_event_ids::text[] as ids from doctor.rule_matches where execution_id = :x"
        " and rule_code = 'INT-005'",
        x=execution,
    )
    assert match[0]["ids"] == [event]
    assert cleaned["error"]["code"] == "V1 801"
