"""Contra um Postgres real. Rodam só com INTEGRATION_DB_URL, no job de E2E do CI."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from aid_api.core.auth import Claims
from aid_api.core.db import tenant_tx
from aid_api.core.errors import ApiError
from aid_api.core.idempotency import IdempotencyStore
from aid_api.integrations.repo import IntegrationRepository
from aid_api.integrations.schemas import IntegrationChange, NewIntegration
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


def claims_for(tenant_id: str, user_id: str, role: str = "viewer", aal: str = "aal1") -> Claims:
    raw = {
        "sub": user_id,
        "role": "authenticated",
        "aal": aal,
        "tenant_id": tenant_id,
        "tenant_role": role,
    }
    return Claims(
        sub=raw["sub"], email=None, aal=aal, tenant_id=tenant_id, tenant_role=role, raw=raw
    )


@pytest_asyncio.fixture
async def user(engine: AsyncEngine) -> AsyncIterator[str]:
    user_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into auth.users (id, instance_id, aud, role, email)"
                " values (:i, '00000000-0000-0000-0000-000000000000', 'authenticated',"
                " 'authenticated', :e)"
            ),
            {"i": user_id, "e": f"{user_id}@integracao.test"},
        )
    yield user_id
    async with engine.begin() as connection:
        await connection.execute(text("delete from auth.users where id = :i"), {"i": user_id})


@pytest_asyncio.fixture
async def tenants(engine: AsyncEngine) -> AsyncIterator[tuple[str, str]]:
    first, second = str(uuid4()), str(uuid4())
    async with engine.begin() as connection:
        for tenant in (first, second):
            await connection.execute(
                text("insert into public.organizations (id, name, slug) values (:i, 'T', :s)"),
                {"i": tenant, "s": f"t-{tenant}"[:40].rstrip("-")},
            )
            await connection.execute(
                text("insert into doctor.tenants (id) values (:i)"), {"i": tenant}
            )
    yield first, second
    async with engine.begin() as connection:
        for tenant in (first, second):
            await connection.execute(
                text("delete from doctor.tenants where id = :i"), {"i": tenant}
            )
            await connection.execute(
                text("delete from public.organizations where id = :i"), {"i": tenant}
            )


async def assert_isolated(
    engine: AsyncEngine, claims: Claims, table: str, column: str, tenant_id: str
) -> None:
    """Isolamento genérico: consulta sem filtro, e o RLS devolve só a Organização do JWT."""
    async with tenant_tx(claims, engine) as connection:
        result = await connection.execute(text(f"select {column}::text from {table}"))  # noqa: S608
        rows = list(result.scalars())
    assert rows == [tenant_id]


@pytest.mark.asyncio
async def test_rls_age_dentro_da_api_sem_filtro_de_tenant(
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    first, second = tenants
    await assert_isolated(engine, claims_for(first, user), "doctor.tenants", "id", first)
    await assert_isolated(engine, claims_for(second, user), "doctor.tenants", "id", second)


@pytest.mark.asyncio
async def test_rota_de_usuario_nunca_usa_service_role(
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    async with tenant_tx(claims_for(tenants[0], user), engine) as connection:
        role = await connection.scalar(text("select current_user"))
        bypass = await connection.scalar(
            text("select rolbypassrls from pg_roles where rolname = current_user")
        )
    assert role == "authenticated"
    assert bypass is False


@pytest.mark.asyncio
async def test_mesma_chave_concorrente_espera_e_devolve_a_resposta_gravada(
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    store = IdempotencyStore(engine)
    claims = claims_for(tenants[0], user)
    first_reserved = asyncio.Event()
    release_first = asyncio.Event()

    async def first() -> None:
        async with store.session(claims) as session:
            assert await session.reserve("k", "h") is None
            first_reserved.set()
            await release_first.wait()
            await session.remember("k", 201, '{"id": "1"}')

    async def second() -> object:
        await first_reserved.wait()
        async with store.session(claims) as session:
            return await session.reserve("k", "h")

    running = asyncio.create_task(first())
    waiting = asyncio.create_task(second())
    await asyncio.sleep(0.3)
    assert not waiting.done(), "a segunda chamada precisa esperar a primeira"
    release_first.set()
    await running
    stored = await waiting
    assert stored is not None
    assert stored.status == 201  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_chave_de_requisicao_que_falhou_fica_livre(
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    store = IdempotencyStore(engine)
    claims = claims_for(tenants[0], user)

    async def failing_request() -> None:
        async with store.session(claims) as session:
            await session.reserve("k2", "h")
            raise RuntimeError

    with pytest.raises(RuntimeError):
        await failing_request()
    async with store.session(claims) as session:
        assert await session.reserve("k2", "h") is None


async def add_admin(engine: AsyncEngine, tenant_id: str, user_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into public.organization_members (org_id, user_id, role)"
                " values (:t, :u, 'member')"
            ),
            {"t": tenant_id, "u": user_id},
        )
        await connection.execute(
            text(
                "insert into doctor.memberships (tenant_id, user_id, role) values (:t, :u, 'admin')"
            ),
            {"t": tenant_id, "u": user_id},
        )


@pytest.mark.asyncio
async def test_integracoes_isoladas_com_nome_unico_por_organizacao(
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    first, second = tenants
    for tenant in tenants:
        await add_admin(engine, tenant, user)
    repository = IntegrationRepository(engine)
    new = NewIntegration(
        name="Pedidos Salesforce → SAP",
        source_system="salesforce",
        target_system="sap",
        environment="prd",
    )
    acme = claims_for(first, user, "admin", "aal2")
    varejo = claims_for(second, user, "admin", "aal2")

    created = await repository.create(acme, new)
    with pytest.raises(ApiError) as duplicated:
        await repository.create(acme, new)
    assert duplicated.value.code == "integration_exists"

    assert await repository.list(varejo, include_archived=True) == []
    await repository.create(varejo, new)
    with pytest.raises(ApiError) as foreign:
        await repository.archive(varejo, created.id)
    assert foreign.value.status == 404

    archived = await repository.archive(acme, created.id)
    assert archived.archived_at is not None
    assert (await repository.archive(acme, created.id)).archived_at == archived.archived_at
    assert await repository.list(acme, include_archived=False) == []
    assert [item.id for item in await repository.list(acme, include_archived=True)] == [created.id]

    with pytest.raises(ApiError) as frozen:
        await repository.update(acme, created.id, IntegrationChange(name="Renomeada"))
    assert frozen.value.code == "integration_archived"
    recreated = await repository.create(acme, new)
    assert recreated.id != created.id


@pytest.mark.asyncio
async def test_admin_rebaixado_com_jwt_antigo_recebe_403_e_nao_404(
    engine: AsyncEngine, tenants: tuple[str, str], user: str
) -> None:
    first, _ = tenants
    await add_admin(engine, first, user)
    repository = IntegrationRepository(engine)
    admin = claims_for(first, user, "admin", "aal2")
    created = await repository.create(
        admin,
        NewIntegration(name="Notas", source_system="sap", target_system="gcp", environment="prd"),
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "update doctor.memberships set role = 'analyst'"
                " where tenant_id = :t and user_id = :u"
            ),
            {"t": first, "u": user},
        )
    for attempt in (
        repository.update(admin, created.id, IntegrationChange(name="Outra")),
        repository.archive(admin, created.id),
    ):
        with pytest.raises(ApiError) as denied:
            await attempt
        assert denied.value.status == 403


@pytest.mark.asyncio
async def test_token_de_ingestao_grava_lote_no_tenant_do_token_sem_service_role(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.ingestion.repo import IngestionRepository
    from aid_api.ingestion.service import new_token
    from aid_api.integrations.repo import IntegrationRepository

    first, _ = tenants
    await add_admin(engine, first, user)
    admin = claims_for(first, user, "admin", "aal2")
    integration = await IntegrationRepository(engine).create(
        admin,
        NewIntegration(name="Notas", source_system="sap", target_system="gcp", environment="prd"),
    )
    token, token_hash, prefix = new_token()
    repository = IngestionRepository()
    import aid_api.core.db as db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    await repository.create_token(admin, "SAP PI", integration.id, token_hash, prefix)
    identity = await repository.identify(token_hash)
    assert (identity.tenant_id, identity.integration_id) == (first, integration.id)
    batch_id = await repository.accept(token_hash, [{"event_id": "e1"}])

    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    "select b.tenant_id::text, b.event_count, o.topic"
                    " from doctor.ingestion_batches b"
                    " join doctor.outbox_messages o on o.payload ->> 'batch_id' = b.id::text"
                    " where b.id = cast(:b as uuid)"
                ),
                {"b": batch_id},
            )
        ).one()
        await connection.execute(
            text("delete from doctor.outbox_messages where tenant_id = :t"), {"t": first}
        )
    assert (row.tenant_id, row.event_count, row.topic) == (first, 1, "ingestion.raw")
    assert token.startswith(prefix)


@pytest.mark.asyncio
async def test_conector_criado_pela_api_guarda_a_credencial_so_no_vault(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.connectors.repo import ConnectorRepository
    from aid_api.connectors.schemas import ConnectorChange, NewConnector
    from aid_api.integrations.repo import IntegrationRepository

    first, _ = tenants
    await add_admin(engine, first, user)
    admin = claims_for(first, user, "admin", "aal2")
    integration = await IntegrationRepository(engine).create(
        admin,
        NewIntegration(name="GCP", source_system="gcp", target_system="sap", environment="prd"),
    )
    import aid_api.core.db as db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    repository = ConnectorRepository()
    created = await repository.create(
        admin,
        NewConnector.model_validate(
            {
                "integration_id": integration.id,
                "provider": "fake",
                "name": "Fake",
                "config": {"pages": 1},
                "credential": "credencial-real",
            }
        ),
    )
    assert "credencial-real" not in created.model_dump_json()
    await repository.update(
        admin,
        created.id,
        ConnectorChange.model_validate({"credential": "trocada"}),
        lambda provider, config: None,
    )
    async with engine.begin() as connection:
        await connection.execute(text("set local role service_role"))
        stored = await connection.scalar(
            text("select doctor.get_connector_secret(cast(:c as uuid))"), {"c": created.id}
        )
        await connection.execute(text("reset role"))
        await connection.execute(
            text("delete from vault.secrets where name = 'doctor/connector/' || :c"),
            {"c": created.id},
        )
    assert stored == "trocada"


async def seed_explorer(engine: AsyncEngine, tenant: str, other: str) -> dict[str, str]:
    """Duas Execuções visíveis, uma fundida e uma de outra Organização com o mesmo execution_id."""
    from aid_security.references import derive_tenant_key, reference_hmac

    ids = {name: str(uuid4()) for name in ("i", "o", "x1", "x2", "x3", "xo", "e1", "e2", "raw")}
    reference = reference_hmac(
        derive_tenant_key(b"chave-mestre-de-teste", UUID(tenant)), "4500012345"
    )
    t0 = datetime(2026, 11, 2, 14, 2, tzinfo=UTC)
    statements = [
        (
            "insert into doctor.integrations (id, tenant_id, name, source_system, target_system,"
            " environment) values (:i, :t, 'Pedidos SF → SAP', 'salesforce', 'sap', 'prd'),"
            " (:o, :other, 'Outra', 'sap', 'gcp', 'prd')",
            {},
        ),
        (
            "insert into doctor.raw_log_objects (id, tenant_id, storage_path, sha256, size_bytes,"
            " source) values (:raw, :t, :path, repeat('a', 64), 10,"
            " 'api')",
            {},
        ),
        (
            "insert into doctor.executions (id, tenant_id, integration_id, status, first_event_at,"
            " last_event_at, duration_ms, event_count, correlation_keys, closed_at) values"
            " (:x1, :t, :i, 'failed', :t0, :t30, 30000, 2, cast(:k1 as jsonb), now()),"
            " (:x2, :t, :i, 'success', :before, :before, 0, 1,"
            '  \'{"execution_id": ["exec-122"]}\', now()),'
            " (:xo, :other, :o, 'success', :t0, :t0, 0, 1,"
            '  \'{"execution_id": ["exec-123"]}\', now())',
            {
                "k1": json.dumps(
                    {
                        "execution_id": ["exec-123"],
                        "trace_id": ["trace-abc"],
                        "business_reference": [reference],
                    }
                )
            },
        ),
        (
            "insert into doctor.executions (id, tenant_id, integration_id, first_event_at,"
            " last_event_at, merged_into, closed_at) values (:x3, :t, :i, :t0, :t0, :x1, now())",
            {},
        ),
        ("select doctor.ensure_event_partition('2026-11-02')", {}),
        (
            "insert into doctor.events (id, tenant_id, integration_id, raw_log_object_id,"
            " timestamp, schema_version, source, operation, severity, error, dedup_key,"
            " execution_id, execution_ref, correlated_by, sanitization_report) values"
            " (:e1, :t, :i, :raw, :t0, '1.0', cast(:src as jsonb), 'BAPI', 'INFO', null, :d1,"
            "  'exec-123', :x1, 'execution_id', '{\"counts\": {}}'),"
            " (:e2, :t, :i, :raw, :t30, '1.0',"
            "  cast(:src as jsonb), 'BAPI', 'ERROR', cast(:err as jsonb), :d2, 'exec-123', :x1,"
            "  'execution_id', '{\"counts\": {\"bearer\": 1}}')",
            {
                "src": json.dumps({"provider": "sap", "service": "PI"}),
                "err": json.dumps({"category": "TIMEOUT", "http_status": 504}),
                "d1": str(uuid4()),
                "d2": str(uuid4()),
            },
        ),
        (
            "insert into doctor.rule_matches (tenant_id, execution_id, rule_code, rule_version,"
            " matched_event_ids)"
            " values (:t, :x1, 'INT-003', '2026.10.1', array[cast(:e2 as uuid)])",
            {},
        ),
        (
            "with created as (insert into doctor.incidents (tenant_id, integration_id, title,"
            " category, severity, rule_code, rule_version, first_seen_at, last_seen_at,"
            " execution_count) values (:t, :i, 'Timeout · Pedidos SF → SAP', 'TIMEOUT',"
            " 'critical', 'INT-003', '2026.10.1', :t0, :t0, 1) returning id)"
            " insert into doctor.incident_executions (tenant_id, incident_id, execution_id)"
            " select :t, id, :x1 from created",
            {},
        ),
    ]
    async with engine.begin() as connection:
        for sql, extra in statements:
            await connection.execute(
                text(sql),
                {
                    **ids,
                    "t": tenant,
                    "other": other,
                    "t0": t0,
                    "t30": t0 + timedelta(seconds=30),
                    "before": t0 - timedelta(hours=1),
                    "path": f"{tenant}/api/lote.json",
                    **extra,
                },
            )
    return {**ids, "reference": reference}


@pytest.mark.asyncio
async def test_explorador_busca_pagina_e_isola(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_api.core.db as db
    from aid_api.executions.repo import ExecutionRepository
    from aid_api.executions.schemas import ExecutionSearch

    first, second = tenants
    seeded = await seed_explorer(engine, first, second)
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    viewer = claims_for(first, user)
    repository = ExecutionRepository()

    async def ids(reference: str | None = None, **query: Any) -> list[str]:
        page = await repository.search(viewer, ExecutionSearch.model_validate(query), reference)
        return [item.id for item in page.items]

    assert await ids() == [seeded["x1"], seeded["x2"]]
    assert await ids(q="trace-abc") == [seeded["x1"]]
    assert await ids(q="exec-122") == [seeded["x2"]]
    # O número do pedido só chega ao banco em HMAC.
    assert await ids(seeded["reference"], q="4500012345") == [seeded["x1"]]
    assert await ids(q="4500012345") == []
    assert await ids(status="success") == [seeded["x2"]]

    page = await repository.search(viewer, ExecutionSearch(limit=1), None)
    assert [item.id for item in page.items] == [seeded["x1"]]
    assert page.items[0].incident is not None
    assert page.items[0].incident.severity == "critical"
    assert page.next_cursor is not None
    assert await ids(limit=1, cursor=page.next_cursor) == [seeded["x2"]]

    detail = await repository.detail(viewer, seeded["x3"])
    assert detail.id == seeded["x1"]
    assert [event.id for event in detail.events] == [seeded["e1"], seeded["e2"]]
    assert detail.events[1].rule_codes == ["INT-003"]
    assert detail.rules[0].category == "TIMEOUT"

    event = await repository.event(viewer, seeded["e2"])
    assert event.sanitization_report == {"counts": {"bearer": 1}}
    # O Log bruto (e de onde ele veio) é de Analyst para cima, como no bucket.
    assert event.raw_log is None
    await add_admin(engine, first, user)
    event = await repository.event(claims_for(first, user, "admin"), seeded["e2"])
    assert event.raw_log is not None
    assert 29 <= event.raw_log.retention_days_left <= 30
    with pytest.raises(ApiError) as missing:
        await repository.detail(viewer, seeded["xo"])
    assert missing.value.status == 404


@pytest.mark.asyncio
async def test_download_do_log_bruto_exige_analyst(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_api.core.db as db
    from aid_api.executions.repo import ExecutionRepository

    first, second = tenants
    seeded = await seed_explorer(engine, first, second)
    await add_admin(engine, first, user)
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    repository = ExecutionRepository()

    async def sign(path: str) -> str:
        return f"https://storage.test/{path}"

    async def broken(path: str) -> str:
        raise ApiError(503, "storage_unavailable", "fora")

    admin = claims_for(first, user, "admin")
    url = await repository.raw_log_download(admin, seeded["raw"], sign)
    assert url == f"https://storage.test/{first}/api/lote.json"
    with pytest.raises(ApiError):
        await repository.raw_log_download(admin, seeded["raw"], broken)
    async with engine.begin() as connection:
        audited = (
            await connection.execute(
                text(
                    "select action, actor_id::text, resource_id from doctor.audit_logs"
                    " where tenant_id = :t and action like 'raw_log.%' order by id"
                ),
                {"t": first},
            )
        ).all()
    # Só o download que gerou URL fica na auditoria.
    assert [tuple(row) for row in audited] == [("raw_log.downloaded", user, seeded["raw"])]
    async with engine.begin() as connection:
        await connection.execute(
            text("update doctor.memberships set role = 'viewer' where user_id = :u"), {"u": user}
        )
    with pytest.raises(ApiError) as denied:
        await repository.raw_log_download(claims_for(first, user, "viewer"), seeded["raw"], sign)
    assert denied.value.status == 403


@pytest.mark.asyncio
async def test_incidentes_busca_contagens_fluxo_e_comentarios(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_api.core.db as db
    from aid_api.incidents.repo import IncidentRepository
    from aid_api.incidents.schemas import IncidentChange, IncidentSearch, NewComment

    first, second = tenants
    seeded = await seed_explorer(engine, first, second)
    await add_admin(engine, first, user)
    async with engine.begin() as connection:
        await connection.execute(
            text("update doctor.memberships set role = 'analyst' where user_id = :u"), {"u": user}
        )
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    analyst = claims_for(first, user, "analyst")
    repository = IncidentRepository()

    page = await repository.search(analyst, IncidentSearch(), None)
    (incident,) = page.items
    assert page.counts == {"open": 1}
    assert incident.number == 1
    for term, reference in (("INC-0001", None), ("1", None), ("trace-abc", None)):
        found = await repository.search(analyst, IncidentSearch(q=term), reference)
        assert [item.id for item in found.items] == [incident.id]
    found = await repository.search(analyst, IncidentSearch(q="4500012345"), seeded["reference"])
    assert [item.id for item in found.items] == [incident.id]
    assert (await repository.search(analyst, IncidentSearch(q="INC-0002"), None)).items == []

    detail = await repository.detail(analyst, incident.id)
    assert [e.id for e in detail.executions] == [seeded["x1"]]
    assert detail.evidence[0].rule_code == "INT-003"
    assert detail.evidence[0].matched_event_ids == [seeded["e2"]]

    changed = await repository.update(
        analyst,
        incident.id,
        IncidentChange.model_validate({"status": "resolved", "resolution_note": "Gateway ok."}),
    )
    assert changed.status == "resolved"
    assert changed.resolution_note == "Gateway ok."
    assert [h.action for h in changed.history] == ["status"]
    with pytest.raises(ApiError) as invalid:
        await repository.update(
            analyst, incident.id, IncidentChange.model_validate({"status": "investigating"})
        )
    assert invalid.value.code == "invalid_transition"
    assert (await repository.search(analyst, IncidentSearch(), None)).counts == {"resolved": 1}

    created = await repository.comment(analyst, incident.id, NewComment(body_md="Resolvido."))
    assert [c.id for c in await repository.comments(analyst, incident.id)] == [created.id]
    with pytest.raises(ApiError) as other:
        await repository.detail(claims_for(second, user, "analyst"), incident.id)
    assert other.value.status == 404


@pytest.mark.asyncio
async def test_conector_mostra_intervalo_checkpoint_e_registros_da_ultima_sincronizacao(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aid_api.connectors.repo import ConnectorRepository
    from aid_api.connectors.schemas import NewConnector
    from aid_api.integrations.repo import IntegrationRepository

    first, _ = tenants
    await add_admin(engine, first, user)
    admin = claims_for(first, user, "admin", "aal2")
    integration = await IntegrationRepository(engine).create(
        admin,
        NewIntegration(
            name="GCP tela", source_system="gcp", target_system="sap", environment="prd"
        ),
    )
    import aid_api.core.db as db

    monkeypatch.setattr(db, "get_engine", lambda: engine)
    repository = ConnectorRepository()
    created = await repository.create(
        admin,
        NewConnector.model_validate(
            {
                "integration_id": integration.id,
                "provider": "fake",
                "name": "Fake tela",
                "config": {"pages": 1},
                "credential": "c",
                "sync_interval_seconds": 60,
            }
        ),
    )
    assert created.sync_interval_seconds == 60
    assert created.last_sync_records is None
    async with engine.begin() as connection:
        for minute, records in ((0, 7), (5, 1204)):
            await connection.execute(
                text(
                    "insert into doctor.connector_syncs"
                    " (tenant_id, connector_id, started_at, finished_at, status, records)"
                    " values (:t, cast(:c as uuid), :s, :s,"
                    " 'succeeded', :r)"
                ),
                {
                    "t": first,
                    "c": created.id,
                    "s": datetime(2026, 11, 3, 10, minute, tzinfo=UTC),
                    "r": records,
                },
            )
        # Em andamento não conta: a contagem é da última que terminou.
        await connection.execute(
            text(
                "insert into doctor.connector_syncs (tenant_id, connector_id, started_at)"
                " values (:t, cast(:c as uuid), '2026-11-03 10:10Z')"
            ),
            {"t": first, "c": created.id},
        )
        await connection.execute(
            text(
                "update doctor.connectors set checkpoint = '{\"page\": 3}'"
                " where id = cast(:c as uuid)"
            ),
            {"c": created.id},
        )
    shown = await repository.get(admin, created.id)
    assert shown.last_sync_records == 1204
    assert shown.checkpoint == {"page": 3}
    assert shown.paused_reason is None
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from vault.secrets where name = 'doctor/connector/' || :c"),
            {"c": created.id},
        )


@pytest.mark.asyncio
async def test_dashboard_bate_com_as_consultas_de_controle(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_api.core.db as db
    from aid_api.dashboard.repo import DashboardRepository

    first, second = tenants
    integration = str(uuid4())
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into doctor.integrations (id, tenant_id, name, source_system,"
                " target_system, environment) values (:i, :t, 'Painel', 'salesforce', 'sap', 'prd')"
            ),
            {"i": integration, "t": first},
        )
        await connection.execute(
            text(
                "insert into doctor.incidents (tenant_id, integration_id, title, category,"
                " severity, rule_code, rule_version, first_seen_at, last_seen_at, status,"
                " resolution_note, resolved_at) values (:t, :i, 'Timeout', 'TIMEOUT', 'high',"
                " 'INT-003', '2026.10.1', :f, :f, 'resolved', 'ok', :r),"
                " (:t, :i, 'Auth', 'AUTH', 'high', 'INT-001', '2026.10.1', :f, :f, 'open',"
                " null, null)"
            ),
            {
                "t": first,
                "i": integration,
                "f": now - timedelta(hours=3),
                "r": now - timedelta(hours=1),
            },
        )
        # Execuções recentes para o agregado: 3 falhas e 1 sucesso na última hora.
        for index, status in enumerate(("failed", "failed", "failed", "success")):
            await connection.execute(
                text(
                    "insert into doctor.executions (tenant_id, integration_id, status,"
                    " first_event_at, last_event_at) values (:t, :i, :s, :at, :at)"
                ),
                {
                    "t": first,
                    "i": integration,
                    "s": status,
                    "at": now - timedelta(minutes=30 + index),
                },
            )
        await connection.execute(text("set local role service_role"))
        await connection.execute(text("select doctor.refresh_execution_stats()"))
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    board = await DashboardRepository().load(claims_for(first, user), "24h", None, None, now)
    assert board.executions.value == 4
    assert board.error_rate.value == 0.75
    assert board.mttr_minutes.value == 120.0
    # O aberto conta; o resolvido entra no MTTR (2 h).
    assert board.open_incidents == 1
    assert sum(bucket.failed for bucket in board.failures) == 3
    assert [(c.category, c.count) for c in board.failures_by_category] == [("UNCLASSIFIED", 3)]
    empty = await DashboardRepository().load(claims_for(second, user), "24h", None, None, now)
    assert empty.executions.value == 0
    assert empty.error_rate.value is None
    assert empty.mttr_minutes.value is None


@pytest.mark.asyncio
async def test_diagnostico_pedido_pela_api_publicado_pelo_worker_e_lido_isolado(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_api.core.db as db
    from aid_api.diagnoses.repo import DiagnosisRepository
    from aid_api.diagnoses.schemas import DiagnosisRequest
    from aid_diagnosis_engine.llm.fake import FakeProvider
    from aid_diagnosis_worker.diagnose import diagnose

    first, second = tenants
    seeded = await seed_explorer(engine, first, second)
    await add_admin(engine, first, user)
    async with engine.begin() as connection:
        await connection.execute(
            text("update doctor.memberships set role = 'analyst' where user_id = :u"), {"u": user}
        )
        incident = await connection.scalar(
            text("select id::text from doctor.incidents where tenant_id = cast(:t as uuid)"),
            {"t": first},
        )
        match = await connection.scalar(
            text("select id::text from doctor.rule_matches where tenant_id = cast(:t as uuid)"),
            {"t": first},
        )
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    analyst = claims_for(first, user, "analyst")
    repository = DiagnosisRepository()

    queued = await repository.request(analyst, incident, DiagnosisRequest(), "req:k1")
    again = await repository.request(analyst, incident, DiagnosisRequest(), "req:k1")
    assert (queued.status, queued.version, again.diagnosis_id) == ("queued", 1, queued.diagnosis_id)

    answer = {
        "classification": "UPSTREAM_TIMEOUT",
        "status": "IDENTIFIED",
        "probable_cause": "O SAP não respondeu dentro do timeout do gateway.",
        "confidence": 0.74,
        "responsible_system": "sap",
        "evidence": [
            {"ref": match, "finding": "INT-003: HTTP 504."},
            {"ref": seeded["e2"], "finding": "Erro após 30 s."},
        ],
        "hypotheses": [],
        "recommendations": [{"text": "Confira no SAP se o pedido existe.", "kind": "verify"}],
        "requires_human_review": False,
    }
    provider = FakeProvider([json.dumps(answer)])
    assert await diagnose(engine, {"diagnosis_id": queued.diagnosis_id}, lambda n: provider) == (
        "published"
    )

    detail = await repository.detail(analyst, queued.diagnosis_id)
    assert (detail.status, detail.stage, detail.confidence, detail.responsible_system) == (
        "published",
        "done",
        0.74,
        "sap",
    )
    assert [(e.kind, e.ref_id, e.execution_id) for e in detail.evidence] == [
        ("rule_match", match, seeded["x1"]),
        ("event", seeded["e2"], seeded["x1"]),
    ]
    assert detail.evidence[1].event_id == seeded["e2"]
    assert detail.evidence[0].event_id is not None
    assert detail.evidence[0].event_timestamp is not None
    assert [r.text for r in detail.recommendations] == ["Confira no SAP se o pedido existe."]
    assert [d.version for d in await repository.for_incident(analyst, incident)] == [1]
    with pytest.raises(ApiError) as other:
        await repository.detail(claims_for(second, user, "analyst"), queued.diagnosis_id)
    assert other.value.status == 404


@pytest.mark.asyncio
async def test_revisao_auditada_e_promocao_do_incidente_resolvido(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_api.core.db as db
    from aid_api.diagnoses.repo import DiagnosisRepository
    from aid_api.diagnoses.schemas import FeedbackRequest
    from aid_api.incidents.repo import IncidentRepository
    from aid_api.incidents.schemas import IncidentChange

    first, second = tenants
    await seed_explorer(engine, first, second)
    await add_admin(engine, first, user)
    async with engine.begin() as connection:
        await connection.execute(
            text("update doctor.memberships set role = 'analyst' where user_id = :u"), {"u": user}
        )
        incident = await connection.scalar(
            text("select id::text from doctor.incidents where tenant_id = cast(:t as uuid)"),
            {"t": first},
        )
        diagnosis = await connection.scalar(
            text(
                "insert into doctor.diagnoses (tenant_id, incident_id, version, status, stage,"
                " requested_mode, mode, processing_key, probable_cause, classification,"
                " published_at) values (cast(:t as uuid), cast(:i as uuid), 1, 'published',"
                " 'done', 'hybrid', 'hybrid', 'k', 'Gateway lento.', 'UPSTREAM_TIMEOUT', now())"
                " returning id::text"
            ),
            {"t": first, "i": incident},
        )
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    analyst = claims_for(first, user, "analyst")
    repository = DiagnosisRepository()

    with pytest.raises(ApiError) as early:
        await repository.promote(analyst, incident)
    assert early.value.code == "not_resolved"
    review = await repository.review(
        analyst,
        diagnosis,
        FeedbackRequest(
            verdict="corrected", correct_category="SAP_LOCK", correct_cause="Lock na VBAK."
        ),
    )
    assert (review.verdict, review.reviewer_id) == ("corrected", user)
    with pytest.raises(ApiError) as twice:
        await repository.review(analyst, diagnosis, FeedbackRequest(verdict="accepted"))
    assert twice.value.code == "already_reviewed"
    detail = await repository.detail(analyst, diagnosis)
    assert detail.requires_human_review is False
    assert [f.verdict for f in detail.feedback] == ["corrected"]

    await IncidentRepository().update(
        analyst,
        incident,
        IncidentChange.model_validate({"status": "resolved", "resolution_note": "VBAK liberada."}),
    )
    assert (await IncidentRepository().detail(analyst, incident)).promotable is True
    document = await repository.promote(analyst, incident)
    promoted = await IncidentRepository().detail(analyst, incident)
    assert (promoted.knowledge_document_id, promoted.promotable) == (document, False)
    with pytest.raises(ApiError) as again:
        await repository.promote(analyst, incident)
    assert again.value.code == "already_promoted"


@pytest.mark.asyncio
async def test_auditoria_registra_a_troca_de_papel_com_a_requisicao_e_so_o_gestor_le(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_api.core.db as db
    import aid_api.core.request_meta as request_meta
    from aid_api.audit.repo import AuditRepository
    from aid_api.audit.schemas import AuditSearch

    first, _ = tenants
    await add_admin(engine, first, user)
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    token = request_meta._meta.set(
        {"ip": "177.10.0.1", "user_agent": "Mozilla/5.0", "request_id": "req-audit"}
    )
    try:
        admin = claims_for(first, user, "admin", aal="aal2")
        async with tenant_tx(admin, engine) as connection:
            await connection.execute(
                text("select doctor.switch_organization(cast(:t as uuid))"), {"t": first}
            )
    finally:
        request_meta._meta.reset(token)

    repository = AuditRepository()
    page = await repository.search(admin, AuditSearch(category="security"))
    [entry] = [item for item in page.items if item.action == "org.switched"]
    assert (entry.actor_id, entry.ip) == (user, "177.10.0.1")
    assert entry.actor_label is not None
    found = await repository.search(admin, AuditSearch(q=entry.actor_label))
    assert any(item.action == "org.switched" for item in found.items)
    # O add_admin passou pelos triggers: o Vínculo novo está na trilha, com o after.
    created = await repository.search(admin, AuditSearch(q="membership.created"))
    # `_` é literal na busca, não curinga nem removido.
    assert (await repository.search(admin, AuditSearch(q="org_switched"))).items == []
    assert (await repository.search(admin, AuditSearch(q="org.switched"))).items
    assert created.items[0].after is not None
    assert created.items[0].after["role"] == "admin"
    assert (await repository.search(admin, AuditSearch(category="diagnosis"))).items == []
    with pytest.raises(ApiError) as denied:
        await repository.search(claims_for(first, user, "admin", aal="aal1"), AuditSearch())
    assert denied.value.status == 403
    await repository.start_export(admin, AuditSearch(category="security"))
    exported = [item async for item in repository.export(admin, AuditSearch(category="security"))]
    assert any(item.action == "org.switched" for item in exported)
    # A exportação também fica na trilha.
    audited = await repository.search(admin, AuditSearch(q="audit.exported"))
    assert [item.action for item in audited.items] == ["audit.exported"]


@pytest.mark.asyncio
async def test_retencao_envio_ao_llm_exclusao_e_titular(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_api.core.db as db
    from aid_api.core.references import reference_of
    from aid_api.privacy.repo import PrivacyRepository
    from aid_api.privacy.schemas import DeletionRequest, RetentionChange

    first, _ = tenants
    seeded = await seed_explorer(engine, first, tenants[1])
    await add_admin(engine, first, user)
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    monkeypatch.setenv("HMAC_MASTER_KEY", "chave-mestre-de-teste")
    admin = claims_for(first, user, "admin", aal="aal2")
    repository = PrivacyRepository()

    settings = await repository.settings(admin)
    assert {r.data_class: r.days for r in settings.retention} == {
        "raw_logs": 30,
        "events": 90,
        "incidents": 180,
        "audit": 365,
    }
    await repository.set_retention(admin, RetentionChange(data_class="events", days=60))
    with pytest.raises(ApiError) as bounds:
        await repository.set_retention(admin, RetentionChange(data_class="audit", days=30))
    assert bounds.value.code == "retention_out_of_bounds"
    await repository.set_llm(admin, False)
    changed = await repository.settings(admin)
    assert ({r.data_class: r.days for r in changed.retention}["events"], changed.llm_enabled) == (
        60,
        False,
    )

    with pytest.raises(ApiError) as not_owner:
        await repository.request_deletion(admin, DeletionRequest(confirmation="x"))
    assert not_owner.value.status == 403

    reference = reference_of(admin, "4500012345")
    assert reference == seeded["reference"]
    assert reference is not None
    async with engine.begin() as connection:
        await connection.execute(
            text("update doctor.events set business_reference = :r where id = cast(:e as uuid)"),
            {"r": reference, "e": seeded["e2"]},
        )
    assert (await repository.find_subject(admin, reference)).events >= 1
    assert await repository.erase_subject(admin, reference) >= 1
    assert (await repository.find_subject(admin, reference)).events == 0


@pytest.mark.asyncio
async def test_uso_da_organizacao_com_os_limites_do_plano(
    engine: AsyncEngine, tenants: tuple[str, str], user: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_api.core.db as db
    from aid_api.usage.repo import UsageRepository

    first, second = tenants
    await add_admin(engine, first, user)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into doctor.usage_records (tenant_id, resource, period_start, quantity)"
                " values (cast(:t as uuid), 'diagnoses_llm',"
                " doctor.usage_period('diagnoses_llm'), 910),"
                " (cast(:o as uuid), 'diagnoses_llm', doctor.usage_period('diagnoses_llm'), 5)"
            ),
            {"t": first, "o": second},
        )
    monkeypatch.setattr(db, "get_engine", lambda: engine)
    usage = await UsageRepository().usage(claims_for(first, user, "admin"))
    by_resource = {item.resource: item for item in usage.resources}
    assert usage.plan == "pilot"
    assert (by_resource["diagnoses_llm"].used, by_resource["diagnoses_llm"].quota) == (910, 1000)
    assert by_resource["members"].used == 1
    assert set(by_resource) == {
        "events_ingested",
        "diagnoses_llm",
        "storage_bytes",
        "connectors_active",
        "members",
    }
