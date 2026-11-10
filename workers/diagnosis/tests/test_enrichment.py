"""Critério do #40: o pedido existe no SAP apesar do 504, então o Diagnóstico recomenda não
reenviar e cita a consulta como Evidência. Ponta a ponta contra o Postgres: o worker de
diagnóstico pede a consulta e espera; o de Conectores consulta um OData falso e o pede de novo."""

import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

import httpx
import pytest
from aid_connector_worker.enrich import run_enrichment
from aid_connectors.odata.connector import ODataConnector
from aid_diagnosis_engine.llm.fake import FakeProvider
from aid_diagnosis_worker.diagnose import diagnose, expire_enrichment
from aid_diagnosis_worker.evaluate import evaluate_execution
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
T0 = datetime(2026, 11, 2, 14, 2, 31, tzinfo=UTC)
SERVICE = "https://s4.acme.com.br/sap/opu/odata/sap/API_SALES_ORDER_SRV"


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


async def rows(engine: AsyncEngine, sql: str, **params: Any) -> list[Any]:
    async with engine.begin() as connection:
        return list((await connection.execute(text(sql), params)).mappings())


class FakeS4:
    def __init__(self, existing: set[str]) -> None:
        self.existing = existing
        self.filters: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        wanted = unquote(parse_qs(urlparse(str(request.url)).query)["$filter"][0])
        self.filters.append(wanted)
        value = wanted.split("'")[1]
        found = (
            [
                {
                    "PurchaseOrderByCustomer": value,
                    "SalesOrder": "12345",
                    "OverallSDProcessStatus": "C",
                }
            ]
            if value in self.existing
            else []
        )
        return httpx.Response(200, json={"d": {"results": found}})


def registry(fake: FakeS4) -> dict[str, Any]:
    async def public(_: str) -> Sequence[str]:
        return ["200.160.2.3"]

    class Wired(ODataConnector):
        def __init__(self) -> None:
            super().__init__(httpx.MockTransport(fake.handler), public)

    return {"odata": Wired}


async def scenario(engine: AsyncEngine, ids: dict[str, str]) -> dict[str, str]:
    """Pedido do Salesforce com timeout no SAP, numa Execução com a chave do Mapa, e o Mapa com
    a consulta no OData do S/4."""
    connector, mapping, execution, event = (str(uuid4()) for _ in range(4))
    await run(
        engine,
        "insert into doctor.connectors (id, tenant_id, integration_id, provider, name, config,"
        " secret_id) values (cast(:c as uuid), :t, :i, 'odata', 'S/4 OData', cast(:cfg as jsonb),"
        " vault.create_secret(:s, 'doctor/connector/' || cast(:c as text)))",
        c=connector,
        t=ids["tenant"],
        i=ids["integration"],
        cfg=json.dumps({"service_url": SERVICE, "version": "v2", "auth": "basic"}),
        s=json.dumps({"username": "AID_READER", "password": "segredo-de-teste"}),
    )
    await run(
        engine,
        "insert into doctor.correlation_mappings (id, tenant_id, integration_id, name, keys,"
        " lookup) values (:m, :t, :i, 'Pedido', cast(:k as jsonb), cast(:l as jsonb))",
        m=mapping,
        t=ids["tenant"],
        i=ids["integration"],
        k=json.dumps([{"system": "sap", "field": "attributes.bstkd"}]),
        l=json.dumps(
            {
                "connector_id": connector,
                "entity": "A_SalesOrder",
                "field": "PurchaseOrderByCustomer",
                "status_field": "OverallSDProcessStatus",
                "id_field": "SalesOrder",
                "pad_left": 0,
            }
        ),
    )
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
        " source, operation, severity, dedup_key, error, attributes, execution_ref, correlated_by,"
        ' cross_keys) values (:id, :t, :i, :at, \'1.0\', \'{"provider": "sap", "service": "PI"}\','
        " 'BAPI_SALESORDER_CREATE', 'ERROR', :d, cast(:e as jsonb), cast(:a as jsonb), :x,"
        " 'cross_system', cast(:k as text[]))",
        id=event,
        t=ids["tenant"],
        i=ids["integration"],
        at=T0,
        d=str(uuid4()),
        e=json.dumps({"category": "TIMEOUT", "http_status": 504, "message": "UPSTREAM_TIMEOUT"}),
        a=json.dumps({"bstkd": "801XX0001"}),
        x=execution,
        k=[f"{mapping}:801XX0001"],
    )
    incident = await evaluate_execution(engine, {"execution_id": execution})
    assert incident is not None
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
    return {"diagnosis": diagnosis, "connector": connector}


async def cleanup(engine: AsyncEngine, ids: dict[str, str]) -> None:
    for table in ("enrichments", "diagnoses", "connectors", "correlation_mappings"):
        await run(engine, f"delete from doctor.{table} where tenant_id = :t", t=ids["tenant"])  # noqa: S608


@pytest.mark.asyncio
async def test_pedido_ja_criado_no_sap_apesar_do_504_nao_reenviar(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    found = await scenario(engine, tenant)
    diagnosis = found["diagnosis"]
    provider = FakeProvider()
    try:
        # 1ª passagem: pede a consulta e espera, sem gastar tentativa.
        assert (
            await diagnose(engine, {"diagnosis_id": diagnosis}, lambda _, _project: provider)
            == "waiting"
        )
        [state] = await rows(
            engine,
            "select status, stage, attempts from doctor.diagnoses where id = cast(:d as uuid)",
            d=diagnosis,
        )
        assert dict(state) == {"status": "queued", "stage": "correlation", "attempts": 0}
        requested = await rows(
            engine,
            "select payload ->> 'diagnosis_id' as d from doctor.outbox_messages"
            " where topic = 'enrichment.requested' and tenant_id = cast(:t as uuid)",
            t=tenant["tenant"],
        )
        assert [r["d"] for r in requested] == [diagnosis]

        # Worker de Conectores: consulta o S/4 e pede o Diagnóstico de novo.
        s4 = FakeS4({"801XX0001"})
        assert await run_enrichment(engine, {"diagnosis_id": diagnosis}, registry(s4)) == 1
        assert s4.filters == ["PurchaseOrderByCustomer eq '801XX0001'"]

        assert (
            await diagnose(engine, {"diagnosis_id": diagnosis}, lambda _, _project: provider)
            == "published"
        )
        recommendations = await rows(
            engine,
            "select text, kind from doctor.diagnosis_recommendations"
            " where diagnosis_id = cast(:d as uuid) order by rank",
            d=diagnosis,
        )
        assert recommendations[0]["text"].startswith(
            "Não reenvie: o pedido 801XX0001 já foi criado no SAP"
        )
        evidence = await rows(
            engine,
            "select e.kind, e.label, n.outcome, n.record_status from doctor.diagnosis_evidence e"
            " join doctor.enrichments n on n.tenant_id = e.tenant_id and n.id = e.enrichment_id"
            " where e.diagnosis_id = cast(:d as uuid)",
            d=diagnosis,
        )
        assert [dict(e) for e in evidence] == [
            {
                "kind": "enrichment",
                "label": "Consulta ao SAP · A_SalesOrder",
                "outcome": "found",
                "record_status": "C",
            }
        ]
    finally:
        await cleanup(engine, tenant)


@pytest.mark.asyncio
async def test_consulta_sem_resposta_expira_e_o_diagnostico_segue_com_a_nota(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    found = await scenario(engine, tenant)
    diagnosis = found["diagnosis"]
    provider = FakeProvider()
    try:
        assert (
            await diagnose(engine, {"diagnosis_id": diagnosis}, lambda _, _project: provider)
            == "waiting"
        )
        # Ainda dentro do prazo: nada expira, e outra entrega continua esperando.
        assert await expire_enrichment(engine) == 0
        assert (
            await diagnose(engine, {"diagnosis_id": diagnosis}, lambda _, _project: provider)
            == "waiting"
        )
        await run(
            engine,
            "update doctor.enrichments set created_at = now() - interval '6 minutes'"
            " where diagnosis_id = cast(:d as uuid)",
            d=diagnosis,
        )
        assert await expire_enrichment(engine) >= 1
        assert (
            await diagnose(engine, {"diagnosis_id": diagnosis}, lambda _, _project: provider)
            == "published"
        )
        [notes] = await rows(
            engine,
            "select verification_notes from doctor.diagnoses where id = cast(:d as uuid)",
            d=diagnosis,
        )
        assert any("Consulta ao SAP indisponível" in n for n in notes["verification_notes"])
    finally:
        await cleanup(engine, tenant)


@pytest.mark.asyncio
async def test_diagnostico_parado_na_fila_com_consultas_respondidas_e_retomado(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    """O pedido de retomada se perdeu (queda do worker de Conectores, ou a resposta chegou
    antes de o Diagnóstico voltar à fila): a rota agendada o pede de novo."""
    from datetime import timedelta

    found = await scenario(engine, tenant)
    diagnosis = found["diagnosis"]
    provider = FakeProvider()
    try:
        assert (
            await diagnose(engine, {"diagnosis_id": diagnosis}, lambda _, _project: provider)
            == "waiting"
        )
        await run_enrichment(engine, {"diagnosis_id": diagnosis}, registry(FakeS4(set())))
        await run(
            engine,
            "delete from doctor.outbox_messages where topic = 'diagnosis.requested'"
            " and payload ->> 'diagnosis_id' = :d",
            d=diagnosis,
        )
        assert await expire_enrichment(engine, idle=timedelta(0)) == 1
        requested = await rows(
            engine,
            "select 1 from doctor.outbox_messages where topic = 'diagnosis.requested'"
            " and payload ->> 'diagnosis_id' = :d",
            d=diagnosis,
        )
        assert len(requested) == 1
        assert (
            await diagnose(engine, {"diagnosis_id": diagnosis}, lambda _, _project: provider)
            == "published"
        )
        # Entrega repetida da consulta, já sem pendentes: pede o Diagnóstico, que ignora.
        assert (
            await run_enrichment(engine, {"diagnosis_id": diagnosis}, registry(FakeS4(set()))) == 0
        )
        assert (
            await diagnose(engine, {"diagnosis_id": diagnosis}, lambda _, _project: provider)
            == "ignored"
        )
    finally:
        await cleanup(engine, tenant)
