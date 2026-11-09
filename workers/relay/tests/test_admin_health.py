"""Status interno dos operadores (ticket #34): as medidas da plataforma com os limites."""

import os
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from aid_relay import handlers
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")


@pytest_asyncio.fixture
async def database() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


@pytest.mark.asyncio
async def test_admin_health_mostra_as_medidas_e_os_limites(
    database: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(handlers, "engine", lambda: database)
    app = FastAPI()
    app.include_router(handlers.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://relay.test"
    ) as client:
        response = await client.get("/admin/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    assert body["checks"]["outbox_lag_seconds"]["limit"] == 300
    assert "connectors_failing" in body["measures"]
    # Só números de todas as Organizações juntas.
    assert all(isinstance(value, int | float) for value in body["measures"].values())
