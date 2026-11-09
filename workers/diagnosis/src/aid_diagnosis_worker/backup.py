"""Backup dos arquivos do Storage (ticket #33): espelho dos buckets do Doctor num bucket GCS em
southamerica-east1, chamado de hora em hora pelo Cloud Scheduler.

- **Remoção primeiro:** o que a origem apagou (retenção, LGPD, exclusão total) sai do espelho
  antes das cópias, e uma cópia com falha não segura a remoção. O bucket tem versionamento: o
  que sai fica 7 dias como versão antiga e depois some.
- **Trava:** se a remoção passar de metade do espelho, nada é removido e o job falha. Uma
  listagem vazia ou errada da origem não apaga o backup.
- **Progresso:** copia em ordem de alteração e grava o ponto a cada bloco. Uma rodada que bate o
  prazo continua na próxima, sem recomeçar do zero."""

import asyncio
import json
import logging
import time
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol
from urllib.parse import quote

import httpx
from aid_db import platform_role
from aid_knowledge.storage import missing
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_diagnosis_worker.retention import KNOWLEDGE, RAW_LOGS

# `doctor-reports` nasce com o Relatório técnico (#32); antes disso, não tem objetos.
BUCKETS = (RAW_LOGS, KNOWLEDGE, "doctor-reports")
JOB = "storage_backup"
# Sobreposição com a rodada anterior: um objeto gravado enquanto ela listava entra de novo
# (sobrescrever é seguro).
OVERLAP = timedelta(minutes=10)
CHUNK = 20
PARALLEL = 8
# Abaixo do timeout do worker (600 s): o que sobrar fica para a próxima rodada.
BUDGET_SECONDS = 420.0
MAX_REMOVAL_SHARE = 0.5
METADATA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
log = logging.getLogger(__name__)


class BackupError(Exception):
    """O backup não terminou como devia (trava da remoção, por exemplo): o job falha e avisa."""


class Source(Protocol):
    async def download(self, bucket: str, path: str) -> bytes | None: ...


class Target(Protocol):
    async def names(self) -> set[str]: ...

    async def put(self, name: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, name: str) -> None: ...


class StorageSource:
    """Leitura dos buckets do Doctor com a chave de serviço, num cliente só para o job inteiro."""

    def __init__(self, url: str, service_key: str, client: httpx.AsyncClient) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1/object"
        self.headers = {"apikey": service_key, "authorization": f"Bearer {service_key}"}
        self.client = client

    async def download(self, bucket: str, path: str) -> bytes | None:
        response = await self.client.get(
            f"{self.base}/{bucket}/{quote(path)}", headers=self.headers
        )
        # Só "objeto inexistente" é None; chave errada ou outro 400 sobe e o job falha.
        if missing(response):
            return None
        response.raise_for_status()
        return response.content


class GcsTarget:
    """Bucket GCS pela API JSON, com o token da service account do Cloud Run."""

    def __init__(self, bucket: str, client: httpx.AsyncClient) -> None:
        self.bucket = bucket
        self.client = client
        self.token: tuple[str, float] | None = None

    async def headers(self) -> dict[str, str]:
        if self.token is None or self.token[1] < time.monotonic() + 60:
            response = await self.client.get(METADATA_URL, headers={"metadata-flavor": "Google"})
            response.raise_for_status()
            body = response.json()
            self.token = (body["access_token"], time.monotonic() + float(body["expires_in"]))
        return {"authorization": f"Bearer {self.token[0]}"}

    async def names(self) -> set[str]:
        found: set[str] = set()
        page: str | None = None
        while True:
            params = {"fields": "items(name),nextPageToken", "maxResults": "1000"}
            if page:
                params["pageToken"] = page
            response = await self.client.get(
                f"https://storage.googleapis.com/storage/v1/b/{self.bucket}/o",
                params=params,
                headers=await self.headers(),
            )
            response.raise_for_status()
            body = response.json()
            found.update(item["name"] for item in body.get("items", []))
            page = body.get("nextPageToken")
            if not page:
                return found

    async def put(self, name: str, data: bytes, content_type: str) -> None:
        response = await self.client.post(
            f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o",
            params={"uploadType": "media", "name": name},
            headers={**await self.headers(), "content-type": content_type},
            content=data,
        )
        response.raise_for_status()

    async def delete(self, name: str) -> None:
        response = await self.client.delete(
            f"https://storage.googleapis.com/storage/v1/b/{self.bucket}/o/{quote(name, safe='')}",
            headers=await self.headers(),
        )
        # Já não existe: o espelho está como deveria.
        if response.status_code != 404:
            response.raise_for_status()


async def source_objects(
    engine: AsyncEngine, buckets: Sequence[str]
) -> tuple[datetime | None, list[Any]]:
    """(ponto da última cópia, objetos da origem em ordem de alteração)."""
    async with engine.begin() as connection:
        await platform_role(connection)
        since = await connection.scalar(
            text("select last_success_at from doctor.platform_jobs where name = :n"), {"n": JOB}
        )
        rows = (
            await connection.execute(
                text(
                    "select bucket_id, name, coalesce(metadata ->> 'mimetype',"
                    " 'application/octet-stream') as type,"
                    " coalesce(updated_at, created_at) as changed"
                    " from storage.objects where bucket_id = any(:b) order by 4, 1, 2"
                ),
                {"b": list(buckets)},
            )
        ).all()
    return since, list(rows)


async def save(engine: AsyncEngine, point: datetime, details: dict[str, int]) -> None:
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "insert into doctor.platform_jobs (name, last_success_at, details)"
                " values (:n, :at, cast(:d as jsonb))"
                " on conflict (name) do update set last_success_at = excluded.last_success_at,"
                " details = excluded.details"
            ),
            {"n": JOB, "at": point, "d": json.dumps(details)},
        )


async def mirror_removals(target: Target, existing: set[str], buckets: Sequence[str]) -> int:
    mirrored = {name for name in await target.names() if name.split("/", 1)[0] in buckets}
    stale = sorted(mirrored - existing)
    if len(stale) > 20 and len(stale) > MAX_REMOVAL_SHARE * len(mirrored):
        raise BackupError(
            f"remoção de {len(stale)} de {len(mirrored)} objetos do espelho recusada:"
            " confira a listagem da origem"
        )
    for name in stale:
        await target.delete(name)
    return len(stale)


async def backup_storage(
    engine: AsyncEngine,
    source: Source,
    target: Target,
    buckets: Sequence[str] = BUCKETS,
    budget: float = BUDGET_SECONDS,
) -> dict[str, int]:
    started = time.monotonic()
    since, rows = await source_objects(engine, buckets)
    existing = {f"{row.bucket_id}/{row.name}" for row in rows}
    removed, removal_error = 0, None
    try:
        removed = await mirror_removals(target, existing, buckets)
    except BackupError as exc:
        removal_error = exc
    floor = since - OVERLAP if since else None
    pending = [row for row in rows if floor is None or row.changed >= floor]
    limit = asyncio.Semaphore(PARALLEL)

    async def copy(row: Any) -> int:
        async with limit:
            data = await source.download(row.bucket_id, row.name)
            if data is None:
                # Apagado entre a listagem e o download: a próxima rodada tira do espelho.
                return 0
            await target.put(f"{row.bucket_id}/{row.name}", data, row.type)
            return 1

    copied, point = 0, since
    for start in range(0, len(pending), CHUNK):
        if time.monotonic() - started > budget:
            break
        chunk = pending[start : start + CHUNK]
        copied += sum(await asyncio.gather(*(copy(row) for row in chunk)))
        # O ponto avança só com o bloco inteiro copiado (falha sobe e a próxima retoma daqui).
        point = chunk[-1].changed
        await save(engine, point, {"copied": copied, "removed": removed})
    left = sum(1 for row in pending if point is None or row.changed > point)
    log.info(
        "backup do Storage: %d copiados, %d removidos do espelho, %d para a próxima rodada",
        copied,
        removed,
        left,
    )
    if removal_error is not None:
        raise removal_error
    return {"copied": copied, "removed": removed, "left": left}
