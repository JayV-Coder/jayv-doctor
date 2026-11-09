"""Backup diário do Storage (ticket #33): espelho no GCS que copia o novo e tira o apagado."""

import os
from uuid import uuid4

import httpx
import pytest
from aid_diagnosis_worker.backup import GcsTarget, backup_storage
from aid_diagnosis_worker.retention import KNOWLEDGE, SupabaseStorage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")
STORAGE_URL = os.environ.get("SUPABASE_URL")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")


class MemoryTarget:
    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}

    async def names(self) -> set[str]:
        return set(self.files)

    async def put(self, name: str, data: bytes, content_type: str) -> None:
        self.files[name] = (data, content_type)

    async def delete(self, name: str) -> None:
        self.files.pop(name, None)


@pytest.mark.skipif(
    URL is None or SERVICE_KEY is None or STORAGE_URL is None,
    reason="sem INTEGRATION_DB_URL, SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY",
)
@pytest.mark.asyncio
async def test_espelho_copia_o_novo_e_tira_o_que_a_origem_apagou(engine: AsyncEngine) -> None:
    assert STORAGE_URL is not None
    assert SERVICE_KEY is not None
    storage = SupabaseStorage(STORAGE_URL, SERVICE_KEY)
    folder = str(uuid4())
    paths = [f"{folder}/a.md", f"{folder}/b.md"]
    async with httpx.AsyncClient() as client:
        for path in paths:
            response = await client.post(
                f"{storage.base}/{KNOWLEDGE}/{path}",
                headers={**storage.headers, "content-type": "text/markdown", "x-upsert": "true"},
                content=f"conteúdo de {path}".encode(),
            )
            response.raise_for_status()
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from doctor.platform_jobs where name = 'storage_backup'")
        )
    target = MemoryTarget()
    # Um arquivo que a origem já não tem: o espelho o tira.
    target.files[f"{KNOWLEDGE}/{folder}/apagado.md"] = (b"x", "text/markdown")
    # O espelho só mexe nos buckets do Doctor.
    target.files["outro-bucket/arquivo"] = (b"x", "text/plain")
    try:
        first = await backup_storage(engine, storage, target, buckets=(KNOWLEDGE,))
        assert first["copied"] >= 2
        assert target.files[f"{KNOWLEDGE}/{paths[0]}"][0] == f"conteúdo de {paths[0]}".encode()
        assert f"{KNOWLEDGE}/{folder}/apagado.md" not in target.files
        assert "outro-bucket/arquivo" in target.files

        # Segunda rodada: só o que mudou desde a anterior (com 1 h de sobreposição) e o apagado.
        await storage.remove(KNOWLEDGE, [paths[1]])
        second = await backup_storage(engine, storage, target, buckets=(KNOWLEDGE,))
        assert second["removed"] == 1
        assert f"{KNOWLEDGE}/{paths[1]}" not in target.files
        async with engine.begin() as connection:
            details = await connection.scalar(
                text("select details from doctor.platform_jobs where name = 'storage_backup'")
            )
        assert details == {"copied": second["copied"], "removed": 1}
    finally:
        await storage.remove(KNOWLEDGE, paths)


@pytest.mark.asyncio
async def test_gcs_usa_o_token_da_service_account_e_pagina_a_listagem() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "metadata.google.internal":
            assert request.headers["metadata-flavor"] == "Google"
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["authorization"] == "Bearer tok"
        if request.method == "GET" and "pageToken" not in request.url.params:
            return httpx.Response(200, json={"items": [{"name": "a"}], "nextPageToken": "p2"})
        if request.method == "GET":
            return httpx.Response(200, json={"items": [{"name": "b"}]})
        if request.method == "DELETE":
            return httpx.Response(404)
        return httpx.Response(200, json={})

    target = GcsTarget("aid-backup", httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    assert await target.names() == {"a", "b"}
    await target.put("doctor-knowledge/t/x y.md", b"oi", "text/markdown")
    await target.delete("doctor-knowledge/t/x y.md")
    upload = next(call for call in calls if call.method == "POST")
    assert upload.url.params["name"] == "doctor-knowledge/t/x y.md"
    assert upload.headers["content-type"] == "text/markdown"
    delete = next(call for call in calls if call.method == "DELETE")
    assert delete.url.raw_path.endswith(b"/o/doctor-knowledge%2Ft%2Fx%20y.md")
    # Um token só para as cinco chamadas.
    assert sum(call.url.host == "metadata.google.internal" for call in calls) == 1
