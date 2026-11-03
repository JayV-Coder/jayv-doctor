"""Leitura do Log bruto no Storage local. Roda só com SUPABASE_SERVICE_ROLE_KEY (job de E2E)."""

import os
from uuid import uuid4

import httpx
import pytest
from aid_ingestion.storage import BUCKET, SupabaseObjectStore

URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
pytestmark = pytest.mark.skipif(KEY is None, reason="sem SUPABASE_SERVICE_ROLE_KEY")


@pytest.mark.asyncio
async def test_le_o_objeto_e_devolve_none_quando_nao_existe() -> None:
    assert KEY is not None
    path = f"{uuid4()}/imports/{uuid4()}/upload.ndjson"
    headers = {"apikey": KEY, "authorization": f"Bearer {KEY}"}
    async with httpx.AsyncClient() as client:
        created = await client.post(
            f"{URL}/storage/v1/object/{BUCKET}/{path}",
            headers={**headers, "content-type": "application/octet-stream"},
            content=b'{"a": 1}\n',
        )
        assert created.status_code == 200, created.text
        try:
            store = SupabaseObjectStore(URL, KEY)
            assert await store.read(path) == b'{"a": 1}\n'
            assert await store.read(f"{uuid4()}/imports/x/upload.csv") is None
        finally:
            await client.request(
                "DELETE",
                f"{URL}/storage/v1/object/{BUCKET}",
                headers=headers,
                json={"prefixes": [path]},
            )
