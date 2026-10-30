from typing import Any

from aid_api.auth import Claims, TokenVerifier, get_claims, get_verifier
from aid_api.main import create_app
from aid_api.me import MeRepository, Organization, Profile, get_me_repository
from fastapi.testclient import TestClient

USER_ID = "00000000-0000-4000-8000-0000000a0001"
TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
PROFILE = Profile(full_name="Ana Souza", avatar_url=None, locale="pt-BR")
ORGANIZATION = Organization(id=TENANT_ID, name="Acme", slug="acme")


class FakeRepository(MeRepository):
    async def profile(self, claims: Claims) -> Profile | None:
        return PROFILE

    async def organizations(self, claims: Claims) -> list[Organization]:
        return [ORGANIZATION] if claims.tenant_id else []


def get_me(claims: Claims) -> Any:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: claims
    app.dependency_overrides[get_me_repository] = FakeRepository
    return TestClient(app).get("/api/v1/me")


def test_me_devolve_perfil_organizacoes_e_papel_ativo() -> None:
    claims = Claims(
        sub=USER_ID, email="ana@acme.test", aal="aal2", tenant_id=TENANT_ID, tenant_role="owner"
    )
    assert get_me(claims).json() == {
        "id": USER_ID,
        "email": "ana@acme.test",
        "aal": "aal2",
        "profile": {"full_name": "Ana Souza", "avatar_url": None, "locale": "pt-BR"},
        "organizations": [{"id": TENANT_ID, "name": "Acme", "slug": "acme"}],
        "active_tenant_id": TENANT_ID,
        "active_role": "owner",
    }


def test_me_sem_organizacao_ativa_nao_falha() -> None:
    response = get_me(Claims(sub=USER_ID, email=None, aal="aal1", tenant_id=None, tenant_role=None))
    assert response.status_code == 200
    assert response.json()["organizations"] == []
    assert response.json()["active_role"] is None


def test_me_sem_token_responde_401() -> None:
    app = create_app()
    app.dependency_overrides[get_verifier] = lambda: TokenVerifier("http://auth.test")
    assert TestClient(app).get("/api/v1/me").status_code == 401
