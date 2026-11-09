"""Backup do Storage (ticket #33): espelho no GCS que copia o novo, tira o apagado, retoma do
ponto e não apaga o espelho por uma listagem errada."""

import os
from urllib.parse import quote
from uuid import uuid4

import httpx
import pytest
from aid_diagnosis_worker.backup import BackupError, GcsTarget, StorageSource, backup_storage
from aid_diagnosis_worker.retention import KNOWLEDGE, SupabaseStorage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")
STORAGE_URL = os.environ.get("SUPABASE_URL")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
real_storage = pytest.mark.skipif(
    URL is None or SERVICE_KEY is None or STORAGE_URL is None,
    reason="sem INTEGRATION_DB_URL, SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY",
)


class MemoryTarget:
    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}

    async def names(self) -> set[str]:
        return set(self.files)

    async def put(self, name: str, data: bytes, content_type: str) -> None:
        self.files[name] = (data, content_type)

    async def delete(self, name: str) -> None:
        self.files.pop(name, None)


async def upload(storage: SupabaseStorage, paths: list[str]) -> None:
    async with httpx.AsyncClient() as client:
        for path in paths:
            response = await client.post(
                f"{storage.base}/{KNOWLEDGE}/{quote(path)}",
                headers={**storage.headers, "content-type": "text/markdown", "x-upsert": "true"},
                content=f"conteúdo de {path}".encode(),
            )
            response.raise_for_status()


async def reset(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from doctor.platform_jobs where name = 'storage_backup'")
        )


@real_storage
@pytest.mark.asyncio
async def test_espelho_copia_o_novo_tira_o_apagado_e_retoma_do_ponto(engine: AsyncEngine) -> None:
    assert STORAGE_URL is not None
    assert SERVICE_KEY is not None
    storage = SupabaseStorage(STORAGE_URL, SERVICE_KEY)
    folder = str(uuid4())
    # Nome com espaço e parênteses: vai codificado na URL (o Storage recusa acento e "#").
    paths = [f"{folder}/a.md", f"{folder}/relatorio 2 (v1).md"]
    await upload(storage, paths)
    await reset(engine)
    target = MemoryTarget()
    target.files[f"{KNOWLEDGE}/{folder}/apagado.md"] = (b"x", "text/markdown")
    target.files["outro-bucket/arquivo"] = (b"x", "text/plain")
    async with httpx.AsyncClient() as client:
        source = StorageSource(STORAGE_URL, SERVICE_KEY, client)
        try:
            # Sem tempo: remove o apagado mesmo sem copiar nada, e deixa tudo para depois.
            paused = await backup_storage(engine, source, target, buckets=(KNOWLEDGE,), budget=-1)
            assert paused["copied"] == 0
            assert paused["left"] >= 2
            assert f"{KNOWLEDGE}/{folder}/apagado.md" not in target.files
            assert "outro-bucket/arquivo" in target.files

            first = await backup_storage(engine, source, target, buckets=(KNOWLEDGE,))
            assert first["left"] == 0
            assert target.files[f"{KNOWLEDGE}/{paths[1]}"][0] == f"conteúdo de {paths[1]}".encode()

            await storage.remove(KNOWLEDGE, [paths[1]])
            second = await backup_storage(engine, source, target, buckets=(KNOWLEDGE,))
            assert second["removed"] == 1
            assert f"{KNOWLEDGE}/{paths[1]}" not in target.files
        finally:
            await storage.remove(KNOWLEDGE, paths)


@real_storage
@pytest.mark.asyncio
async def test_listagem_vazia_nao_apaga_o_espelho(engine: AsyncEngine) -> None:
    target = MemoryTarget()
    for n in range(30):
        target.files[f"{KNOWLEDGE}/{uuid4()}/{n}.md"] = (b"x", "text/markdown")
    await reset(engine)

    class Nothing:
        async def download(self, bucket: str, path: str) -> bytes | None:
            return None

    # Bucket sem nenhum objeto na origem: a remoção dos 30 do espelho é recusada.
    target.files = {f"doctor-vazio/{k}": v for k, v in target.files.items()}
    with pytest.raises(BackupError):
        await backup_storage(engine, Nothing(), target, buckets=("doctor-vazio",))
    assert len(target.files) == 30


@pytest.mark.asyncio
async def test_400_que_nao_e_objeto_inexistente_falha_em_vez_de_pular() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sumiu.md"):
            return httpx.Response(400, json={"error": "not_found", "message": "Object not found"})
        return httpx.Response(400, json={"statusCode": "403", "error": "Unauthorized"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        source = StorageSource("http://storage.test", "chave", client)
        assert await source.download(KNOWLEDGE, "t/sumiu.md") is None
        with pytest.raises(httpx.HTTPStatusError):
            await source.download(KNOWLEDGE, "t/outro.md")


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

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        target = GcsTarget("aid-backup", client)
        assert await target.names() == {"a", "b"}
        await target.put("doctor-knowledge/t/x y.md", b"oi", "text/markdown")
        await target.delete("doctor-knowledge/t/x y.md")
    upload_call = next(call for call in calls if call.method == "POST")
    assert upload_call.url.params["name"] == "doctor-knowledge/t/x y.md"
    assert upload_call.headers["content-type"] == "text/markdown"
    delete = next(call for call in calls if call.method == "DELETE")
    assert delete.url.raw_path.endswith(b"/o/doctor-knowledge%2Ft%2Fx%20y.md")
    assert sum(call.url.host == "metadata.google.internal" for call in calls) == 1
