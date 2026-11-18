from typing import Any

from aid_api.core.auth import Claims, get_claims
from aid_api.core.errors import ApiError
from aid_api.main import create_app
from aid_api.orgs.repo import (
    OrganizationRepository,
    get_organization_repository,
    not_a_member,
    slug_taken,
)
from aid_api.orgs.schemas import EnabledOrganization, NewOrganization
from fastapi.testclient import TestClient

USER_ID = "00000000-0000-4000-8000-0000000a0001"
TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
CLAIMS = Claims(sub=USER_ID, email=None, aal="aal1", tenant_id=None, tenant_role=None)
PAYLOAD = {
    "name": "Acme Consultoria",
    "slug": "acme-consultoria",
    "segment": "Varejo",
    "llm_provider": "vertex",
    "dpa_accepted": True,
}


class FakeRepository(OrganizationRepository):
    def __init__(self, error: ApiError | None = None) -> None:
        self.error = error
        self.created: list[NewOrganization] = []
        self.switched: list[str] = []
        self.enabled: list[tuple[str, EnabledOrganization]] = []

    async def create(self, claims: Claims, organization: NewOrganization) -> str:
        if self.error:
            raise self.error
        self.created.append(organization)
        return TENANT_ID

    async def switch(self, claims: Claims, tenant_id: str) -> None:
        if self.error:
            raise self.error
        self.switched.append(tenant_id)

    async def enable(self, claims: Claims, org_id: str, settings: EnabledOrganization) -> str:
        if self.error:
            raise self.error
        self.enabled.append((org_id, settings))
        return org_id


def client(repository: FakeRepository) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: CLAIMS
    app.dependency_overrides[get_organization_repository] = lambda: repository
    return TestClient(app)


def test_cria_organizacao_e_devolve_o_id() -> None:
    repository = FakeRepository()
    response = client(repository).post("/api/v1/orgs", json=PAYLOAD)
    assert response.status_code == 201
    assert response.json() == {"id": TENANT_ID}
    assert repository.created[0].slug == "acme-consultoria"


def test_sem_aceite_do_dpa_nao_cria() -> None:
    repository = FakeRepository()
    response = client(repository).post("/api/v1/orgs", json={**PAYLOAD, "dpa_accepted": False})
    assert response.status_code == 422
    assert repository.created == []


def test_nome_so_com_espacos_nao_chega_ao_banco() -> None:
    repository = FakeRepository()
    response = client(repository).post("/api/v1/orgs", json={**PAYLOAD, "name": "   "})
    assert response.status_code == 422
    assert repository.created == []


def test_payload_nao_define_tenant_nem_papel() -> None:
    response = client(FakeRepository()).post(
        "/api/v1/orgs", json={**PAYLOAD, "tenant_id": TENANT_ID, "role": "owner"}
    )
    assert response.status_code == 422


def test_identificador_repetido_responde_409() -> None:
    response = client(FakeRepository(slug_taken())).post("/api/v1/orgs", json=PAYLOAD)
    assert response.status_code == 409
    assert response.json()["code"] == "slug_taken"


def test_troca_de_organizacao_responde_204() -> None:
    repository = FakeRepository()
    response = client(repository).post(f"/api/v1/orgs/{TENANT_ID}/switch")
    assert response.status_code == 204
    assert repository.switched == [TENANT_ID]


def test_troca_sem_vinculo_responde_404() -> None:
    response: Any = client(FakeRepository(not_a_member())).post(f"/api/v1/orgs/{TENANT_ID}/switch")
    assert response.status_code == 404
    assert response.json()["code"] == "not_a_member"


ENABLE = {"segment": "Indústria", "llm_provider": "anthropic", "dpa_accepted": True}


def test_owner_ativa_o_doctor_numa_organizacao_que_ja_existe() -> None:
    repository = FakeRepository()
    response = client(repository).post(f"/api/v1/orgs/{TENANT_ID}/enable", json=ENABLE)
    assert response.status_code == 201
    assert response.json() == {"id": TENANT_ID}
    [(org_id, settings)] = repository.enabled
    assert (org_id, settings.segment, settings.llm_provider) == (
        TENANT_ID,
        "Indústria",
        "anthropic",
    )


def test_ativar_exige_o_aceite_do_dpa_e_nao_aceita_nome_nem_papel() -> None:
    repository = FakeRepository()
    for body in (
        {**ENABLE, "dpa_accepted": False},
        {**ENABLE, "name": "Outra"},
        {**ENABLE, "role": "owner"},
        {**ENABLE, "segment": "x"},
    ):
        assert (
            client(repository).post(f"/api/v1/orgs/{TENANT_ID}/enable", json=body).status_code
            == 422
        )
    assert repository.enabled == []


def test_quem_nao_e_owner_no_jayv_coder_nao_ativa() -> None:
    from aid_api.orgs.repo import not_owner

    response = client(FakeRepository(not_owner())).post(
        f"/api/v1/orgs/{TENANT_ID}/enable", json=ENABLE
    )
    assert response.status_code == 403
    assert response.json()["code"] == "not_owner"


def test_ativar_de_novo_responde_409() -> None:
    from aid_api.orgs.repo import already_enabled

    response = client(FakeRepository(already_enabled())).post(
        f"/api/v1/orgs/{TENANT_ID}/enable", json=ENABLE
    )
    assert response.status_code == 409
    assert response.json()["code"] == "already_enabled"
