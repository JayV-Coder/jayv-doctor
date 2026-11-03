"""Job de retenção e exclusão total contra Postgres real (ticket #29)."""

import importlib.util
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from aid_diagnosis_worker.retention import KNOWLEDGE, RAW_LOGS, SupabaseStorage, run_retention
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")
STORAGE_URL = os.environ.get("SUPABASE_URL")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
# O Storage local de verdade (o Postgres não deixa apagar objeto direto nas tabelas dele).
pytestmark = pytest.mark.skipif(
    URL is None or SERVICE_KEY is None or STORAGE_URL is None,
    reason="sem INTEGRATION_DB_URL, SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY",
)
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "verify_tenant_deleted.py"


class RecordingStorage(SupabaseStorage):
    """O Storage real, guardando o que o job pediu para remover."""

    def __init__(self) -> None:
        assert STORAGE_URL is not None
        assert SERVICE_KEY is not None
        super().__init__(STORAGE_URL, SERVICE_KEY)
        self.removed: list[tuple[str, str]] = []

    async def remove(self, bucket: str, paths: Sequence[str]) -> None:
        self.removed += [(bucket, path) for path in paths]
        await super().remove(bucket, paths)

    async def put(self, bucket: str, path: str) -> None:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base}/{bucket}/{path}",
                headers={**self.headers, "content-type": "text/plain", "x-upsert": "true"},
                content=b"conteudo",
            )
        response.raise_for_status()

    async def listed(self, bucket: str, prefix: str) -> list[str]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base}/list/{bucket}",
                headers=self.headers,
                json={"prefix": prefix, "limit": 100},
            )
        response.raise_for_status()
        return [item["name"] for item in response.json() if item.get("id")]


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


@pytest.mark.asyncio
async def test_log_bruto_vencido_sai_do_storage_e_do_banco(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    old, recent = str(uuid4()), str(uuid4())
    storage = RecordingStorage()
    for ident, age in ((old, timedelta(days=40)), (recent, timedelta(days=1))):
        path = f"{tenant['tenant']}/api/{ident}.json"
        await run(
            engine,
            "insert into doctor.raw_log_objects (id, tenant_id, storage_path, sha256, size_bytes,"
            " source, created_at, expires_at) values (:i, :t, :p, repeat('a', 64), 10, 'api',"
            " :created, now() + interval '30 days')",
            i=ident,
            t=tenant["tenant"],
            p=path,
            created=datetime.now(UTC) - age,
        )
        await storage.put(RAW_LOGS, path)
    result = await run_retention(engine, storage)
    assert result["raw_logs"] >= 1
    assert (RAW_LOGS, f"{tenant['tenant']}/api/{old}.json") in storage.removed
    async with engine.begin() as connection:
        left = set(
            (
                await connection.execute(
                    text(
                        "select id::text from doctor.raw_log_objects"
                        " where tenant_id = cast(:t as uuid)"
                    ),
                    {"t": tenant["tenant"]},
                )
            ).scalars()
        )
        purge = await connection.scalar(
            text(
                "select after from doctor.audit_logs where tenant_id = cast(:t as uuid)"
                " and action = 'retention.purge'"
            ),
            {"t": tenant["tenant"]},
        )
    # Listagem do Storage: só o recente ficou.
    assert left == {recent}
    assert await storage.listed(RAW_LOGS, f"{tenant['tenant']}/api/") == [f"{recent}.json"]
    assert purge["raw_logs"] == 1


@pytest.mark.asyncio
async def test_exclusao_total_vencida_nao_deixa_nada(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    gone = str(uuid4())
    await run(
        engine,
        "insert into public.organizations (id, name, slug) values (:t, 'Some', :s)",
        t=gone,
        s=f"s-{gone[:30]}",
    )
    await run(
        engine,
        "insert into doctor.tenants (id, deletion_requested_at, deletion_scheduled_for)"
        " values (:t, now() - interval '8 days', now() - interval '1 day')",
        t=gone,
    )
    await run(
        engine,
        "insert into doctor.integrations (id, tenant_id, name, source_system, target_system,"
        " environment) values (:i, :t, 'Pedidos', 'salesforce', 'sap', 'prd')",
        i=str(uuid4()),
        t=gone,
    )
    storage = RecordingStorage()
    await storage.put(RAW_LOGS, f"{gone}/imports/x/upload.ndjson")
    await storage.put(KNOWLEDGE, f"{gone}/y/document.md")
    connector = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into doctor.connectors (id, tenant_id, integration_id, provider, name,"
                " secret_id) select :c, :t, id, 'gcp', 'Logging', vault.create_secret('{}', :n)"
                " from doctor.integrations where tenant_id = cast(:t as uuid)"
            ),
            {"c": connector, "t": gone, "n": f"doctor/connector/{connector}"},
        )
    try:
        result = await run_retention(engine, storage)
        assert result["deleted_tenants"] >= 1
        assert result["failures"] == 0
        assert {bucket for bucket, path in storage.removed if path.startswith(gone)} == {
            RAW_LOGS,
            KNOWLEDGE,
        }
        spec = importlib.util.spec_from_file_location("verify_tenant_deleted", SCRIPT)
        assert spec is not None
        assert spec.loader is not None
        verify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify)
        assert URL is not None
        assert await verify.leftovers(URL, gone) == []
        async with engine.begin() as connection:
            receipt = await connection.scalar(
                text(
                    "select removed from doctor.deletion_receipts"
                    " where tenant_id = cast(:t as uuid)"
                ),
                {"t": gone},
            )
        assert receipt["storage_objects"] == 2
        assert receipt["vault_secrets"] == 1
    finally:
        await run(engine, "delete from doctor.deletion_receipts where tenant_id = :t", t=gone)
        await run(engine, "delete from doctor.tenants where id = :t", t=gone)
        await run(engine, "delete from public.organizations where id = :t", t=gone)


@pytest.mark.asyncio
async def test_retencao_de_logs_brutos_acima_de_30_dias_vale(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    await run(
        engine,
        "insert into doctor.retention_policies (tenant_id, data_class, days)"
        " values (:t, 'raw_logs', 90)",
        t=tenant["tenant"],
    )
    ident = str(uuid4())
    await run(
        engine,
        "insert into doctor.raw_log_objects (id, tenant_id, storage_path, sha256, size_bytes,"
        " source, created_at) values (:i, :t, :p, repeat('a', 64), 10, 'api', :created)",
        i=ident,
        t=tenant["tenant"],
        p=f"{tenant['tenant']}/api/{ident}.json",
        created=datetime.now(UTC) - timedelta(days=40),
    )
    async with engine.begin() as connection:
        expires = await connection.scalar(
            text("select expires_at from doctor.raw_log_objects where id = cast(:i as uuid)"),
            {"i": ident},
        )
    # Vence pela política (90 dias), não pelo padrão de 30: o de 40 dias fica.
    assert expires > datetime.now(UTC) + timedelta(days=49)
    await run(
        engine, "delete from doctor.retention_policies where tenant_id = :t", t=tenant["tenant"]
    )


@pytest.mark.asyncio
async def test_armazenamento_medido_por_organizacao(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    from aid_diagnosis_worker.retention import measure_storage

    storage = RecordingStorage()
    path = f"{tenant['tenant']}/api/{uuid4()}.json"
    await storage.put(RAW_LOGS, path)
    try:
        await measure_storage(engine)
        async with engine.begin() as connection:
            used = await connection.scalar(
                text(
                    "select quantity from doctor.usage_records where tenant_id = cast(:t as uuid)"
                    " and resource = 'storage_bytes'"
                ),
                {"t": tenant["tenant"]},
            )
        assert used == len(b"conteudo")
    finally:
        await storage.remove(RAW_LOGS, [path])
