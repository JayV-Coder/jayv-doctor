"""Backup diário dos arquivos do Storage (ticket #33): espelho dos buckets do Doctor num bucket
GCS em southamerica-east1, chamado pelo Cloud Scheduler às 04:00 BRT. Copia o que é novo ou
mudou desde a última rodada e tira do espelho o que a origem apagou (retenção, LGPD, exclusão
total). O bucket tem versionamento: o que sai fica 7 dias como versão antiga e depois some, e a
retenção do backup acompanha a da origem."""

import json
import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import quote

import httpx
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from aid_diagnosis_worker.retention import KNOWLEDGE, RAW_LOGS

BUCKETS = (RAW_LOGS, KNOWLEDGE, "doctor-reports")
JOB = "storage_backup"
# Sobreposição com a rodada anterior: objeto gravado durante ela entra de novo (sobrescrever é
# seguro), e nada escapa entre as duas.
OVERLAP = timedelta(hours=1)
METADATA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
log = logging.getLogger(__name__)


class Source(Protocol):
    async def download(self, bucket: str, path: str) -> bytes | None: ...


class Target(Protocol):
    async def names(self) -> set[str]: ...

    async def put(self, name: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, name: str) -> None: ...


class GcsTarget:
    """Bucket GCS pela API JSON, com o token da service account do Cloud Run."""

    def __init__(self, bucket: str, client: httpx.AsyncClient | None = None) -> None:
        self.bucket = bucket
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
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


async def changed_since(
    engine: AsyncEngine, buckets: Sequence[str]
) -> tuple[datetime | None, list[tuple[str, str, str]], set[str]]:
    """(última rodada, objetos a copiar, todos os nomes que existem na origem)."""
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
                    " from storage.objects where bucket_id = any(:b)"
                ),
                {"b": list(buckets)},
            )
        ).all()
    floor = since - OVERLAP if since else None
    copy = [
        (row.bucket_id, row.name, row.type) for row in rows if floor is None or row.changed >= floor
    ]
    return since, copy, {f"{row.bucket_id}/{row.name}" for row in rows}


async def backup_storage(
    engine: AsyncEngine, source: Source, target: Target, buckets: Sequence[str] = BUCKETS
) -> dict[str, int]:
    started = datetime.now(UTC)
    _, copy, existing = await changed_since(engine, buckets)
    copied = 0
    for bucket, path, content_type in copy:
        data = await source.download(bucket, path)
        if data is None:
            # Apagado entre a listagem e o download: a próxima rodada tira do espelho.
            continue
        await target.put(f"{bucket}/{path}", data, content_type)
        copied += 1
    removed = 0
    for name in sorted(await target.names()):
        if name.split("/", 1)[0] in buckets and name not in existing:
            await target.delete(name)
            removed += 1
    # Só com tudo copiado e o espelho limpo: falha no meio repete a janela amanhã.
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "insert into doctor.platform_jobs (name, last_success_at, details)"
                " values (:n, :at, cast(:d as jsonb))"
                " on conflict (name) do update set last_success_at = excluded.last_success_at,"
                " details = excluded.details"
            ),
            {"n": JOB, "at": started, "d": json.dumps({"copied": copied, "removed": removed})},
        )
    log.info("backup do Storage: %d copiados, %d removidos do espelho", copied, removed)
    return {"copied": copied, "removed": removed}
