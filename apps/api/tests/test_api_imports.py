from datetime import UTC, datetime
from typing import Any

import pytest
from aid_api.core.auth import Claims, get_bearer_token, get_claims
from aid_api.core.errors import ApiError
from aid_api.imports.content import MISMATCH
from aid_api.imports.repo import CreatedRow, ImportRepository, get_import_repository
from aid_api.imports.schemas import Import, NewImport
from aid_api.imports.storage import Head, Storage, get_storage
from aid_api.main import create_app
from fastapi.testclient import TestClient

USER_ID = "00000000-0000-4000-8000-0000000a0001"
TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
INTEGRATION_ID = "00000000-0000-4000-8000-0000000001a1"
IMPORT_ID = "00000000-0000-4000-8000-0000000000f1"
PATH = f"{TENANT_ID}/imports/{IMPORT_ID}/sap-orders.ndjson"
SHA = "a" * 64
NEW = {
    "integration_id": INTEGRATION_ID,
    "filename": "sap-orders.ndjson",
    "size_bytes": 1200,
    "sha256": SHA,
}


def an_import(**overrides: Any) -> Import:
    data: dict[str, Any] = {
        "id": IMPORT_ID,
        "integration_id": INTEGRATION_ID,
        "filename": "sap-orders.ndjson",
        "size_bytes": 1200,
        "format": "ndjson",
        "status": "pending",
        "duplicate_of": None,
        "total_lines": 0,
        "accepted": 0,
        "rejected": 0,
        "duplicates": 0,
        "secrets_removed": 0,
        "error": None,
        "created_at": datetime(2026, 11, 2, tzinfo=UTC),
        **overrides,
    }
    return Import.model_validate(data)


class FakeRepository(ImportRepository):
    def __init__(self, created: CreatedRow | None = None, current: Import | None = None) -> None:
        self.created = created or CreatedRow(
            id=IMPORT_ID, status="pending", error=None, duplicate_of=None, storage_path=PATH
        )
        self.current = current or an_import()
        self.completed: int | None = None
        self.rejected_with: str | None = None

    async def list(self, claims: Claims) -> list[Import]:
        return [self.current]

    async def create(self, claims: Claims, new: NewImport) -> CreatedRow:
        return self.created

    async def get(self, claims: Claims, target: str) -> tuple[Import, str]:
        return self.current, PATH

    async def complete(self, claims: Claims, target: str, size: int) -> Import:
        self.completed = size
        return an_import(status="uploaded", size_bytes=size)

    async def reject(self, claims: Claims, target: str, reason: str, size: int) -> Import:
        self.rejected_with = reason
        return an_import(status="rejected", error=reason)


class FakeStorage(Storage):
    def __init__(self, head: Head | None = None) -> None:
        self.stored = head
        self.signed: list[tuple[str, str]] = []
        self.read: list[str] = []

    async def sign_upload(self, token: str, path: str) -> str:
        self.signed.append((token, path))
        return f"https://storage.test/upload/{path}?token=assinado"

    async def head(self, token: str, path: str, limit: int) -> Head | None:
        self.read.append(path)
        return self.stored


def claims(role: str | None, aal: str = "aal1") -> Claims:
    return Claims(
        sub=USER_ID,
        email="ana@acme.test",
        aal=aal,
        tenant_id=TENANT_ID if role else None,
        tenant_role=role,
    )


def client(
    identity: Claims, repository: FakeRepository | None = None, storage: FakeStorage | None = None
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: identity
    app.dependency_overrides[get_bearer_token] = lambda: "jwt-do-usuario"
    app.dependency_overrides[get_import_repository] = lambda: repository or FakeRepository()
    app.dependency_overrides[get_storage] = lambda: storage or FakeStorage()
    return TestClient(app)


# Matriz do ticket #6: "Importar logs" é de Owner, Admin e Analyst, sem exigir MFA.
@pytest.mark.parametrize(
    ("role", "allowed"), [("owner", True), ("admin", True), ("analyst", True), ("viewer", False)]
)
def test_quem_importa_logs(role: str, allowed: bool) -> None:
    response = client(claims(role)).post("/api/v1/imports", json=NEW)
    assert response.status_code == (201 if allowed else 403)


@pytest.mark.parametrize("role", ["owner", "admin", "analyst", "viewer"])
def test_todo_papel_lista_as_importacoes(role: str) -> None:
    response = client(claims(role)).get("/api/v1/imports")
    assert response.status_code == 200
    assert response.json()[0]["filename"] == "sap-orders.ndjson"


def test_importacao_pendente_recebe_url_assinada_com_o_jwt_do_usuario() -> None:
    storage = FakeStorage()
    response = client(claims("analyst"), storage=storage).post("/api/v1/imports", json=NEW)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["upload_url"].startswith("https://storage.test/upload/")
    assert storage.signed == [("jwt-do-usuario", PATH)]


def test_importacao_recusada_nao_recebe_url() -> None:
    rejected = CreatedRow(
        id=IMPORT_ID,
        status="rejected",
        error="Formato não permitido",
        duplicate_of=None,
        storage_path=None,
    )
    storage = FakeStorage()
    response = client(claims("analyst"), FakeRepository(created=rejected), storage).post(
        "/api/v1/imports", json={**NEW, "filename": "pedidos.xml"}
    )
    assert response.status_code == 201
    assert response.json() == {
        "id": IMPORT_ID,
        "status": "rejected",
        "error": "Formato não permitido",
        "duplicate_of": None,
        "upload_url": None,
    }
    assert storage.signed == []


@pytest.mark.parametrize(
    "body",
    [
        {**NEW, "tenant_id": TENANT_ID},
        {**NEW, "sha256": "nao-e-hash"},
        {**NEW, "size_bytes": -1},
        {**NEW, "filename": ""},
    ],
    ids=["tenant-no-payload", "sha256", "tamanho", "nome-vazio"],
)
def test_payload_invalido_vira_422(body: dict[str, Any]) -> None:
    response = client(claims("analyst")).post("/api/v1/imports", json=body)
    assert response.status_code == 422


def complete(repository: FakeRepository, storage: FakeStorage) -> Any:
    return client(claims("analyst"), repository, storage).post(
        f"/api/v1/imports/{IMPORT_ID}/complete"
    )


def test_concluir_confere_o_conteudo_e_registra_o_tamanho_do_storage() -> None:
    repository = FakeRepository()
    storage = FakeStorage(Head(data=b'{"severity": "error"}\n', size=1180))
    response = complete(repository, storage)
    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"
    assert repository.completed == 1180
    assert storage.read == [PATH]


def test_conteudo_de_outro_formato_rejeita_a_importacao() -> None:
    repository = FakeRepository()
    response = complete(repository, FakeStorage(Head(data=b"<?xml version='1.0'?>", size=21)))
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert repository.rejected_with == MISMATCH
    assert repository.completed is None


def test_concluir_sem_o_arquivo_no_storage_vira_409() -> None:
    response = complete(FakeRepository(), FakeStorage(None))
    assert response.status_code == 409
    assert response.json()["code"] == "upload_missing"


def test_concluir_importacao_que_nao_esta_pendente_vira_409_sem_ler_o_storage() -> None:
    storage = FakeStorage(Head(data=b"{}", size=2))
    response = complete(FakeRepository(current=an_import(status="uploaded")), storage)
    assert response.status_code == 409
    assert response.json()["code"] == "import_not_pending"
    assert storage.read == []


def test_viewer_nao_conclui() -> None:
    response = client(claims("viewer")).post(f"/api/v1/imports/{IMPORT_ID}/complete")
    assert response.status_code == 403


def test_erro_do_storage_vira_503() -> None:
    class Down(FakeStorage):
        async def sign_upload(self, token: str, path: str) -> str:
            raise ApiError(503, "storage_unavailable", "Armazenamento indisponível.")

    response = client(claims("analyst"), storage=Down()).post("/api/v1/imports", json=NEW)
    assert response.status_code == 503
    assert response.json()["code"] == "storage_unavailable"
