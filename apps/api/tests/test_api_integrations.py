from datetime import UTC, datetime
from typing import Any

import pytest
from aid_api.core.auth import Claims, get_claims
from aid_api.core.errors import ApiError
from aid_api.integrations.repo import (
    IntegrationRepository,
    get_integration_repository,
    integration_exists,
)
from aid_api.integrations.schemas import Integration, IntegrationChange, NewIntegration
from aid_api.main import create_app
from fastapi.testclient import TestClient

USER_ID = "00000000-0000-4000-8000-0000000a0001"
TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
TARGET_ID = "00000000-0000-4000-8000-0000000000f1"

NEW = {
    "name": "Pedidos Salesforce → SAP",
    "source_system": "salesforce",
    "target_system": "sap",
    "environment": "prd",
}


def integration(**overrides: Any) -> Integration:
    data: dict[str, Any] = {
        "id": TARGET_ID,
        "description": None,
        "owner_team": None,
        "archived_at": None,
        "created_at": datetime(2026, 11, 2, tzinfo=UTC),
        **NEW,
        **overrides,
    }
    return Integration.model_validate(data)


class FakeRepository(IntegrationRepository):
    def __init__(self, error: ApiError | None = None) -> None:
        self.error = error
        self.listed_archived: bool | None = None
        self.created: NewIntegration | None = None
        self.change: dict[str, Any] | None = None

    def fail(self) -> None:
        if self.error:
            raise self.error

    async def list(self, claims: Claims, *, include_archived: bool) -> list[Integration]:
        self.fail()
        self.listed_archived = include_archived
        return [integration()]

    async def create(self, claims: Claims, new: NewIntegration) -> Integration:
        self.fail()
        self.created = new
        return integration(**new.model_dump())

    async def update(self, claims: Claims, target: str, change: IntegrationChange) -> Integration:
        self.fail()
        self.change = change.model_dump(exclude_unset=True)
        return integration(**self.change)

    async def archive(self, claims: Claims, target: str) -> Integration:
        self.fail()
        return integration(archived_at=datetime(2026, 11, 3, tzinfo=UTC))


def claims(role: str | None, aal: str = "aal2") -> Claims:
    return Claims(
        sub=USER_ID,
        email="ana@acme.test",
        aal=aal,
        tenant_id=TENANT_ID if role else None,
        tenant_role=role,
    )


def client(identity: Claims, repository: FakeRepository | None = None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: identity
    app.dependency_overrides[get_integration_repository] = lambda: repository or FakeRepository()
    return TestClient(app)


WRITES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("POST", "/api/v1/integrations", NEW),
    ("PATCH", f"/api/v1/integrations/{TARGET_ID}", {"name": "Notas SAP → GCP"}),
    ("POST", f"/api/v1/integrations/{TARGET_ID}/archive", None),
]


# Matriz do ticket #6: "Gerenciar integrações e conectores" é de Owner e Admin.
@pytest.mark.parametrize(("method", "path", "body"), WRITES)
@pytest.mark.parametrize(
    ("role", "allowed"), [("owner", True), ("admin", True), ("analyst", False), ("viewer", False)]
)
def test_so_owner_e_admin_alteram_integracoes(
    method: str, path: str, body: dict[str, Any] | None, role: str, allowed: bool
) -> None:
    response = client(claims(role)).request(method, path, json=body)
    if allowed:
        assert response.status_code < 300
    else:
        assert response.status_code == 403
        assert response.json()["code"] == "forbidden"


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
def test_alterar_integracao_exige_mfa(method: str, path: str, body: dict[str, Any] | None) -> None:
    response = client(claims("admin", aal="aal1")).request(method, path, json=body)
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


@pytest.mark.parametrize("role", ["owner", "admin", "analyst", "viewer"])
def test_todo_papel_lista_as_integracoes(role: str) -> None:
    response = client(claims(role, aal="aal1")).get("/api/v1/integrations")
    assert response.status_code == 200
    assert response.json()[0]["name"] == NEW["name"]


def test_lista_padrao_esconde_as_arquivadas() -> None:
    repository = FakeRepository()
    client(claims("viewer"), repository).get("/api/v1/integrations")
    assert repository.listed_archived is False
    client(claims("viewer"), repository).get("/api/v1/integrations?include_archived=true")
    assert repository.listed_archived is True


def test_sem_organizacao_ativa_nao_lista() -> None:
    response = client(claims(None)).get("/api/v1/integrations")
    assert response.status_code == 403
    assert response.json()["code"] == "no_active_tenant"


def test_cria_e_devolve_201() -> None:
    repository = FakeRepository()
    response = client(claims("admin"), repository).post("/api/v1/integrations", json=NEW)
    assert response.status_code == 201
    assert response.json()["environment"] == "prd"
    assert response.json()["error_rate_24h"] is None
    assert repository.created is not None
    assert repository.created.name == NEW["name"]


@pytest.mark.parametrize(
    "body",
    [
        {**NEW, "tenant_id": TENANT_ID},
        {**NEW, "environment": "qa"},
        {**NEW, "source_system": "oracle"},
        {**NEW, "name": "x"},
        {**NEW, "description": "a" * 501},
    ],
    ids=["tenant-no-payload", "ambiente", "sistema", "nome-curto", "descricao-longa"],
)
def test_payload_invalido_vira_422(body: dict[str, Any]) -> None:
    response = client(claims("admin")).post("/api/v1/integrations", json=body)
    assert response.status_code == 422


def test_nome_e_ambiente_repetidos_viram_409() -> None:
    repository = FakeRepository(integration_exists())
    response = client(claims("admin"), repository).post("/api/v1/integrations", json=NEW)
    assert response.status_code == 409
    assert response.json()["code"] == "integration_exists"


def test_patch_altera_so_o_que_veio() -> None:
    repository = FakeRepository()
    response = client(claims("owner"), repository).patch(
        f"/api/v1/integrations/{TARGET_ID}", json={"owner_team": "Squad Pedidos"}
    )
    assert response.status_code == 200
    assert repository.change == {"owner_team": "Squad Pedidos"}


@pytest.mark.parametrize(
    "body",
    [{}, {"name": None}, {"environment": None}, {"archived_at": None}],
    ids=["vazio", "nome-nulo", "ambiente-nulo", "arquivamento-por-patch"],
)
def test_patch_invalido_vira_422(body: dict[str, Any]) -> None:
    response = client(claims("owner")).patch(f"/api/v1/integrations/{TARGET_ID}", json=body)
    assert response.status_code == 422


def test_arquivar_devolve_a_integracao_arquivada() -> None:
    response = client(claims("admin")).post(f"/api/v1/integrations/{TARGET_ID}/archive")
    assert response.status_code == 200
    assert response.json()["archived_at"] is not None


def test_integracao_de_outro_tenant_vira_404() -> None:
    repository = FakeRepository(ApiError(404, "not_found", "Registro não encontrado."))
    response = client(claims("admin"), repository).post(f"/api/v1/integrations/{TARGET_ID}/archive")
    assert response.status_code == 404
