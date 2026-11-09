"""Job diário de retenção e exclusão (ticket #29), chamado pelo Cloud Scheduler às 03:00 BRT:
Logs brutos vencidos (Storage primeiro, depois a linha), a purga de cada Organização pela
retenção dela, as partições inteiras que ninguém mais precisa e as exclusões totais com a
carência vencida. O pg_cron do projeto é do jayv-coder (ADR-0009), por isso o job é do worker."""

import logging
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
log = logging.getLogger(__name__)


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

    async def download(self, bucket: str, path: str) -> bytes | None:
        """O arquivo, para o backup (#33); `None` se já foi apagado."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.get(f"{self.base}/{bucket}/{path}", headers=self.headers)
        if response.status_code in (400, 404):
            return None
        response.raise_for_status()
        return response.content


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


async def tenant_objects(engine: AsyncEngine, tenant: str, bucket: str) -> list[str]:
    async with engine.begin() as connection:
        await platform_role(connection)
        paths = (
            await connection.execute(
                text("select name from storage.objects where bucket_id = :b and name like :prefix"),
                {"b": bucket, "prefix": f"{tenant}/%"},
            )
        ).scalars()
        return list(paths)


async def delete_tenant(engine: AsyncEngine, storage: Storage, tenant: str) -> str:
    # Congela primeiro: nada novo chega ao Storage depois da listagem.
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text("select doctor.freeze_tenant(cast(:t as uuid))"), {"t": tenant}
        )
    removed = 0
    for bucket in (RAW_LOGS, KNOWLEDGE):
        found = await tenant_objects(engine, tenant, bucket)
        if found:
            await storage.remove(bucket, found)
            removed += len(found)
    async with engine.begin() as connection:
        await platform_role(connection)
        receipt = await connection.scalar(
            text("select doctor.purge_tenant(cast(:t as uuid), :n)::text"),
            {"t": tenant, "n": removed},
        )
    # O que tiver chegado no meio (escrita que já estava em curso) sai também.
    for bucket in (RAW_LOGS, KNOWLEDGE):
        late = await tenant_objects(engine, tenant, bucket)
        if late:
            await storage.remove(bucket, late)
    return str(receipt)


async def delete_tenants(engine: AsyncEngine, storage: Storage) -> tuple[list[str], int]:
    """Exclusão total com a carência vencida. Uma Organização que falhe não impede as outras: ela
    continua vencida e o job tenta de novo amanhã."""
    async with engine.begin() as connection:
        await platform_role(connection)
        due = (
            await connection.execute(
                text("select tenant_id::text from doctor.due_tenant_deletions()")
            )
        ).scalars()
        tenants = list(due)
    receipts, failures = [], 0
    for tenant in tenants:
        try:
            receipts.append(await delete_tenant(engine, storage, tenant))
        except Exception:
            failures += 1
            log.exception("exclusão total falhou para a Organização %s", tenant)
    return receipts, failures


async def measure_storage(engine: AsyncEngine) -> None:
    """Armazenamento de cada Organização (Cota `storage_bytes`, #31): a soma dos arquivos das
    pastas dela nos buckets do Doctor, gravada uma vez por dia."""
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "select doctor.set_usage(t.id, 'storage_bytes', coalesce(s.bytes, 0)::bigint)"
                " from doctor.tenants t left join ("
                " select split_part(o.name, '/', 1) as tenant,"
                " sum(coalesce((o.metadata ->> 'size')::bigint, 0)) as bytes"
                " from storage.objects o where o.bucket_id in (:raw, :knowledge)"
                " group by 1) s on s.tenant = t.id::text"
                " where t.status in ('active', 'suspended')"
            ),
            {"raw": RAW_LOGS, "knowledge": KNOWLEDGE},
        )


async def run_retention(engine: AsyncEngine, storage: Storage) -> dict[str, int]:
    raw_logs = await purge_raw_logs(engine, storage)
    async with engine.begin() as connection:
        await platform_role(connection)
        tenants = list(
            (
                await connection.execute(
                    # Suspensa também: a retenção vale enquanto houver dado guardado.
                    text(
                        "select id::text from doctor.tenants"
                        " where status in ('active', 'suspended')"
                        " and deletion_scheduled_for is null"
                    )
                )
            ).scalars()
        )
    failures = 0
    for tenant in tenants:
        # Uma transação por Organização: uma que falhe não desfaz nem impede a das outras.
        try:
            async with engine.begin() as connection:
                await platform_role(connection)
                await connection.execute(
                    text("select doctor.purge_tenant_data(cast(:t as uuid), :n)"),
                    {"t": tenant, "n": raw_logs.get(tenant, 0)},
                )
        except Exception:
            failures += 1
            log.exception("retenção falhou para a Organização %s", tenant)
    dropped: list[str] = []
    try:
        async with engine.begin() as connection:
            await platform_role(connection)
            dropped = list(
                await connection.scalar(text("select doctor.drop_expired_partitions()")) or []
            )
    except Exception:
        failures += 1
        log.exception("drop das partições vencidas falhou")
    try:
        await measure_storage(engine)
    except Exception:
        failures += 1
        log.exception("medição do armazenamento falhou")
    receipts, deletion_failures = await delete_tenants(engine, storage)
    return {
        "raw_logs": sum(raw_logs.values()),
        "tenants": len(tenants),
        "partitions": len(dropped),
        "deleted_tenants": len(receipts),
        "failures": failures + deletion_failures,
    }
