import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from aid_api.core.auth import Claims, get_claims
from aid_api.core.storage import Storage, get_storage
from aid_api.executions.repo import ExecutionRepository, get_execution_repository
from aid_api.executions.schemas import ExecutionPage, ExecutionSearch
from aid_api.main import create_app
from aid_security.references import derive_tenant_key, reference_hmac
from fastapi.testclient import TestClient

TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
RAW_ID = "00000000-0000-4000-8000-0000000000aa"
ORDER = "4500012345"


class FakeRepository(ExecutionRepository):
    def __init__(self) -> None:
        self.searches: list[tuple[ExecutionSearch, str | None]] = []

    async def search(
        self, claims: Claims, query: ExecutionSearch, reference: str | None
    ) -> ExecutionPage:
        self.searches.append((query, reference))
        return ExecutionPage(items=[], next_cursor=None)

    async def raw_log_download(self, claims: Claims, target: str, sign: Any) -> str:
        url: str = await sign(f"{TENANT_ID}/api/lote.json")
        return url


class FakeStorage(Storage):
    async def sign_download(self, token: str, path: str, seconds: int) -> str:
        return f"https://storage.test/{path}?expira={seconds}"


def client(repository: FakeRepository, role: str = "viewer") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: Claims(
        sub="u", email=None, aal="aal1", tenant_id=TENANT_ID, tenant_role=role
    )
    app.dependency_overrides[get_execution_repository] = lambda: repository
    app.dependency_overrides[get_storage] = lambda: FakeStorage()
    return TestClient(app, headers={"authorization": "Bearer jwt"})


def test_busca_pela_referencia_manda_so_o_hmac(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("HMAC_MASTER_KEY", "chave-mestre-de-teste")
    repository = FakeRepository()
    caplog.set_level(logging.DEBUG)
    response = client(repository).post("/api/v1/executions/search", json={"q": ORDER})
    assert response.status_code == 200
    (_, reference) = repository.searches[0]
    key = derive_tenant_key(b"chave-mestre-de-teste", UUID(TENANT_ID))
    assert reference == reference_hmac(key, ORDER)
    assert ORDER not in caplog.text


def test_sem_chave_a_busca_fica_nos_ids_tecnicos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HMAC_MASTER_KEY", raising=False)
    repository = FakeRepository()
    client(repository).post("/api/v1/executions/search", json={"q": "trace-abc"})
    assert repository.searches[0][1] is None


@pytest.mark.parametrize(
    "body",
    [{"limit": 51}, {"status": "talvez"}, {"q": ""}, {"extra": 1}, {"q": "x" * 257}],
)
def test_busca_invalida_responde_422(body: dict[str, Any]) -> None:
    response = client(FakeRepository()).post("/api/v1/executions/search", json=body)
    assert response.status_code == 422


def test_filtros_de_periodo_usam_from_e_to() -> None:
    repository = FakeRepository()
    client(repository).post(
        "/api/v1/executions/search",
        json={"from": "2026-11-02T00:00:00Z", "to": "2026-11-02T23:59:59Z", "environment": "prd"},
    )
    query = repository.searches[0][0]
    assert query.since == datetime(2026, 11, 2, tzinfo=UTC)
    assert query.environment == "prd"


def test_viewer_nao_baixa_o_log_bruto() -> None:
    response = client(FakeRepository()).get(f"/api/v1/raw-logs/{RAW_ID}/download")
    assert response.status_code == 403


def test_analyst_recebe_url_de_5_minutos() -> None:
    response = client(FakeRepository(), "analyst").get(f"/api/v1/raw-logs/{RAW_ID}/download")
    assert response.status_code == 200
    assert response.json() == {
        "url": f"https://storage.test/{TENANT_ID}/api/lote.json?expira=300",
        "expires_in": 300,
    }
