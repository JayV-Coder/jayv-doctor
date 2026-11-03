"""Job diário de retenção e exclusão (ticket #29), chamado pelo Cloud Scheduler às 03:00 BRT:
Logs brutos vencidos (Storage primeiro, depois a linha), a purga de cada Organização pela
retenção dela, as partições inteiras que ninguém mais precisa e as exclusões totais com a
carência vencida. O pg_cron do projeto é do jayv-coder (ADR-0009), por isso o job é do worker."""

from collections import Counter
from collections.abc import Sequence
from typing import Protocol

import httpx
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

RAW_LOGS = "doctor-raw-logs"
KNOWLEDGE = "doctor-knowledge"
BATCH = 500


class Storage(Protocol):
    async def remove(self, bucket: str, paths: Sequence[str]) -> None: ...


class SupabaseStorage:
    """Remoção em lote pela API do Storage (o arquivo some do backend, não só a linha)."""

    def __init__(self, url: str, service_key: str) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1/object"
        self.headers = {"apikey": service_key, "authorization": f"Bearer {service_key}"}

    async def remove(self, bucket: str, paths: Sequence[str]) -> None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            for start in range(0, len(paths), 1000):
                response = await client.request(
                    "DELETE",
                    f"{self.base}/{bucket}",
                    headers=self.headers,
                    json={"prefixes": list(paths[start : start + 1000])},
                )
                # Falha sobe: a linha só sai depois do arquivo, e o job repete amanhã.
                response.raise_for_status()


async def purge_raw_logs(engine: AsyncEngine, storage: Storage) -> Counter[str]:
    removed: Counter[str] = Counter()
    while True:
        async with engine.begin() as connection:
            await platform_role(connection)
            rows = (
                await connection.execute(
                    text(
                        "select id::text, tenant_id::text, storage_path"
                        " from doctor.expired_raw_logs(:n)"
                    ),
                    {"n": BATCH},
                )
            ).all()
        if not rows:
            return removed
        await storage.remove(RAW_LOGS, [row.storage_path for row in rows])
        async with engine.begin() as connection:
            await platform_role(connection)
            await connection.execute(
                text("select doctor.forget_raw_logs(cast(:ids as uuid[]))"),
                {"ids": [row.id for row in rows]},
            )
        removed.update(row.tenant_id for row in rows)
        if len(rows) < BATCH:
            return removed


async def delete_tenants(engine: AsyncEngine, storage: Storage) -> list[str]:
    """Exclusão total com a carência vencida: os arquivos das duas pastas da Organização saem do
    Storage, e depois o banco (Vault e cascade) e o comprovante."""
    receipts = []
    async with engine.begin() as connection:
        await platform_role(connection)
        due = (
            await connection.execute(
                text("select tenant_id::text from doctor.due_tenant_deletions()")
            )
        ).scalars()
        tenants = list(due)
    for tenant in tenants:
        removed = 0
        for bucket in (RAW_LOGS, KNOWLEDGE):
            async with engine.begin() as connection:
                await platform_role(connection)
                paths = (
                    await connection.execute(
                        text(
                            "select name from storage.objects"
                            " where bucket_id = :b and name like :prefix"
                        ),
                        {"b": bucket, "prefix": f"{tenant}/%"},
                    )
                ).scalars()
                found = list(paths)
            if found:
                await storage.remove(bucket, found)
                removed += len(found)
        async with engine.begin() as connection:
            await platform_role(connection)
            receipt = await connection.scalar(
                text("select doctor.purge_tenant(cast(:t as uuid), :n)::text"),
                {"t": tenant, "n": removed},
            )
        receipts.append(str(receipt))
    return receipts


async def run_retention(engine: AsyncEngine, storage: Storage) -> dict[str, int]:
    raw_logs = await purge_raw_logs(engine, storage)
    async with engine.begin() as connection:
        await platform_role(connection)
        tenants = list(
            (
                await connection.execute(
                    text(
                        "select id::text from doctor.tenants"
                        " where status = 'active' and deletion_scheduled_for is null"
                    )
                )
            ).scalars()
        )
    for tenant in tenants:
        # Uma transação por Organização: uma que falhe não desfaz a das outras.
        async with engine.begin() as connection:
            await platform_role(connection)
            await connection.execute(
                text("select doctor.purge_tenant_data(cast(:t as uuid), :n)"),
                {"t": tenant, "n": raw_logs.get(tenant, 0)},
            )
    async with engine.begin() as connection:
        await platform_role(connection)
        dropped = await connection.scalar(text("select doctor.drop_expired_partitions()"))
    receipts = await delete_tenants(engine, storage)
    return {
        "raw_logs": sum(raw_logs.values()),
        "tenants": len(tenants),
        "partitions": len(dropped or []),
        "deleted_tenants": len(receipts),
    }
