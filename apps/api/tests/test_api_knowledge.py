from typing import Any

import pytest
from aid_api.core.auth import Claims, get_claims
from aid_api.core.storage import Storage, get_storage
from aid_api.knowledge.repo import KnowledgeRepository, get_knowledge_repository
from aid_api.knowledge.router import get_provider_for
from aid_api.knowledge.schemas import KnowledgeHit, NewKnowledgeDocument
from aid_api.main import create_app
from aid_diagnosis_engine.llm.base import LLMUnavailableError
from aid_diagnosis_engine.llm.fake import FakeProvider
from fastapi.testclient import TestClient

TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
DOC = "00000000-0000-4000-8000-0000000007a1"


class FakeRepository(KnowledgeRepository):
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def create(self, claims: Claims, new: NewKnowledgeDocument) -> tuple[str, str]:
        self.calls.append(("create", new))
        return DOC, f"{TENANT_ID}/{DOC}/runbook.md"

    async def delete(self, claims: Claims, target: str) -> str | None:
        self.calls.append(("delete", target))
        return f"{TENANT_ID}/{DOC}/runbook.md"

    async def llm_provider(self, claims: Claims) -> str:
        return "anthropic"

    async def search(
        self, claims: Claims, query: str, k: int, embedding: Any, model: str | None
    ) -> list[KnowledgeHit]:
        self.calls.append(("search", (query, embedding is not None, model)))
        return []


class FakeStorage(Storage):
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    async def sign_upload(self, token: str, path: str, bucket: str = "x") -> str:
        return f"https://storage.test/{bucket}/{path}"

    async def delete(self, token: str, path: str, bucket: str) -> None:
        self.deleted.append((bucket, path))


class Down(FakeProvider):
    async def embed(self, texts: Any, *, input_type: Any) -> list[list[float]]:
        raise LLMUnavailableError("fora")


def client(
    repository: FakeRepository,
    role: str = "viewer",
    storage: FakeStorage | None = None,
    provider: FakeProvider | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: Claims(
        sub="u", email=None, aal="aal1", tenant_id=TENANT_ID, tenant_role=role
    )
    app.dependency_overrides[get_knowledge_repository] = lambda: repository
    app.dependency_overrides[get_storage] = lambda: storage or FakeStorage()
    chosen = provider or FakeProvider()
    app.dependency_overrides[get_provider_for] = lambda: lambda name: chosen
    return TestClient(app, headers={"authorization": "Bearer jwt"})


def test_analyst_envia_e_recebe_url_no_bucket_do_conhecimento() -> None:
    repository = FakeRepository()
    response = client(repository, "analyst").post(
        "/api/v1/knowledge/documents",
        json={
            "title": "Runbook",
            "filename": "runbook.md",
            "content_type": "text/markdown",
            "size_bytes": 100,
        },
    )
    assert response.status_code == 201
    assert response.json()["upload_url"].startswith("https://storage.test/doctor-knowledge/")


@pytest.mark.parametrize(
    "body",
    [
        {"title": "x", "filename": "a.exe", "content_type": "application/x", "size_bytes": 1},
        {
            "title": "x",
            "filename": "a.md",
            "content_type": "text/markdown",
            "size_bytes": 21 * 2**20,
        },
        {"title": "x", "filename": "../a.md", "content_type": "text/markdown", "size_bytes": 1},
    ],
)
def test_formato_tamanho_e_nome_invalidos(body: dict[str, Any]) -> None:
    response = client(FakeRepository(), "analyst").post("/api/v1/knowledge/documents", json=body)
    assert response.status_code == 422


def test_viewer_nao_envia_nem_remove() -> None:
    api = client(FakeRepository())
    assert api.delete(f"/api/v1/knowledge/documents/{DOC}").status_code == 403


def test_remover_apaga_o_arquivo_do_bucket() -> None:
    storage = FakeStorage()
    response = client(FakeRepository(), "analyst", storage).delete(
        f"/api/v1/knowledge/documents/{DOC}"
    )
    assert response.status_code == 204
    assert storage.deleted == [("doctor-knowledge", f"{TENANT_ID}/{DOC}/runbook.md")]


def test_busca_hibrida_e_so_texto_com_o_provedor_fora() -> None:
    repository = FakeRepository()
    response = client(repository).post("/api/v1/knowledge/search", json={"q": "VL10 bloqueado"})
    assert response.json()["mode"] == "hybrid"
    hybrid = repository.calls[-1]
    assert hybrid == ("search", ("VL10 bloqueado", True, "fake"))
    response = client(repository, provider=Down()).post(
        "/api/v1/knowledge/search", json={"q": "VL10 bloqueado"}
    )
    assert response.json()["mode"] == "text"
    text_only = repository.calls[-1]
    assert text_only == ("search", ("VL10 bloqueado", False, None))
