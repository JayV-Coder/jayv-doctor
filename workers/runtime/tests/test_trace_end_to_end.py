"""Critério de aceite do ticket #34: um Evento injetado é rastreável da API até a gravação em
`doctor.events` num único trace (API → outbox → relay → Pub/Sub → worker de ingestão)."""

import base64
import hashlib
import json
import os
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from aid_connectors.base import stable_uuid7
from aid_observability.tracing import traceparent, tracer
from aid_relay.publisher import PubSubPublisher
from aid_relay.relay import Stats, publish_batch
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
KEY = "chave-mestre-de-teste-do-trace-0123456789"
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")

EXPORTER = InMemorySpanExporter()


class Capture(PubSubPublisher):
    def __init__(self) -> None:
        super().__init__("aid-test")
        self.sent: list[tuple[str, bytes, dict[str, str]]] = []

    async def publish(self, client: Any, topic: str, messages: Any) -> None:
        self.sent += [(topic, data, dict(attributes)) for data, attributes in messages]


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


@pytest_asyncio.fixture
async def ingestion(engine: AsyncEngine) -> AsyncIterator[dict[str, str]]:
    ids = {"tenant": str(uuid4()), "integration": str(uuid4()), "token_id": str(uuid4())}
    ids["token"] = "aid_ing_" + secrets.token_urlsafe(32)
    async with engine.begin() as connection:
        for sql, params in (
            (
                "insert into public.organizations (id, name, slug) values (:t, 'Trace', :s)",
                {"t": ids["tenant"], "s": f"trace-{ids['tenant'][:8]}"},
            ),
            ("insert into doctor.tenants (id) values (:t)", {"t": ids["tenant"]}),
            (
                "insert into doctor.integrations (id, tenant_id, name, source_system,"
                " target_system, environment) values (:i, :t, 'Pedidos', 'salesforce', 'sap',"
                " 'prd')",
                {"i": ids["integration"], "t": ids["tenant"]},
            ),
            (
                "insert into doctor.ingestion_tokens (id, tenant_id, name, integration_id,"
                " token_hash, prefix) values (:k, :t, 'trace', :i, :h, 'aid_ing_trac')",
                {
                    "k": ids["token_id"],
                    "t": ids["tenant"],
                    "i": ids["integration"],
                    "h": hashlib.sha256(ids["token"].encode()).hexdigest(),
                },
            ),
            ("select doctor.ensure_event_partition(now()::date)", {}),
        ):
            await connection.execute(text(sql), params)
    yield ids
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from doctor.tenants where id = :t"), {"t": ids["tenant"]}
        )
        await connection.execute(
            text("delete from public.organizations where id = :t"), {"t": ids["tenant"]}
        )


@pytest.mark.asyncio
async def test_evento_injetado_na_api_chega_a_events_no_mesmo_trace(
    engine: AsyncEngine, ingestion: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert URL is not None
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(EXPORTER))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setenv("SUPABASE_DB_URL", URL)
    monkeypatch.setenv("HMAC_MASTER_KEY", KEY)
    from aid_api.core import db
    from aid_api.main import create_app as api_app
    from aid_ingestion import handlers as ingestion_handlers
    from aid_worker.main import create_app as worker_app
    from aid_worker.main import handlers_for

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    monkeypatch.setattr(ingestion_handlers, "engine", lambda: engine)
    api = api_app()
    FastAPIInstrumentor.instrument_app(api, tracer_provider=provider)

    # 1. O sistema do cliente envia o Evento dentro de um trace.
    event = {
        "schema_version": "1.0",
        "event_id": stable_uuid7(str(uuid4()), datetime.now(UTC)),
        "integration_id": ingestion["integration"],
        "timestamp": datetime.now(UTC).isoformat(),
        "source": {"provider": "sap", "service": "PI"},
        "operation": "BAPI_SALESORDER_CREATEFROMDAT2",
        "severity": "ERROR",
    }
    with tracer.start_as_current_span("cliente") as root:
        header = traceparent()
        assert header is not None
        transport = httpx.ASGITransport(app=api)
        async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
            response = await client.post(
                "/api/v1/ingestion/events",
                json={"events": [event]},
                headers={"authorization": f"Bearer {ingestion['token']}", "traceparent": header},
            )
    assert response.status_code == 202, response.text
    assert response.json()["accepted"] == 1, response.text
    trace_id = f"{root.get_span_context().trace_id:032x}"

    # 2. A mensagem da outbox guarda o trace da requisição.
    async with engine.begin() as connection:
        rows = (
            await connection.execute(
                text(
                    "select id, tenant_id::text, topic, payload, traceparent"
                    " from doctor.outbox_messages where tenant_id = cast(:t as uuid)"
                    " and topic = 'ingestion.raw'"
                ),
                {"t": ingestion["tenant"]},
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].traceparent.split("-")[1] == trace_id

    # 3. O relay publica o trace como atributo da mensagem.
    publisher = Capture()
    async with httpx.AsyncClient() as client:
        await publish_batch(client, publisher, list(rows), Stats())
    topic, data, attributes = publisher.sent[0]
    assert attributes["traceparent"] == rows[0].traceparent

    # 4. O worker de ingestão recebe o push e grava em doctor.events no mesmo trace.
    EXPORTER.clear()
    envelope = {
        "message": {
            "data": base64.b64encode(data).decode(),
            "messageId": "m-trace",
            "attributes": attributes,
        },
        "subscription": f"projects/aid/subscriptions/{topic}.push",
    }
    worker = worker_app("ingestion", handlers_for("ingestion"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=worker), base_url="http://worker.test"
    ) as client:
        pushed = await client.post("/pubsub", json=envelope)
    assert pushed.status_code == 204, pushed.text
    spans = {span.name: span for span in EXPORTER.get_finished_spans()}
    assert f"{spans['pubsub ingestion.raw'].context.trace_id:032x}" == trace_id
    assert f"{spans['doctor.events insert'].context.trace_id:032x}" == trace_id
    async with engine.begin() as connection:
        stored = await connection.scalar(
            text("select count(*) from doctor.events where tenant_id = cast(:t as uuid)"),
            {"t": ingestion["tenant"]},
        )
    assert stored == 1
    assert json.loads(data)["batch_id"]
