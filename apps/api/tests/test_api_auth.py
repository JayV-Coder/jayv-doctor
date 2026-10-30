from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import jwt
import pytest
from aid_api.auth import Claims, TokenVerifier, get_verifier, require_aal2
from aid_api.main import create_app
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends
from fastapi.testclient import TestClient

ISSUER = "http://auth.test/auth/v1"
USER_ID = "00000000-0000-4000-8000-0000000a0001"
TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


@dataclass
class StaticKeyVerifier(TokenVerifier):
    def signing_key(self, token: str) -> Any:
        return PRIVATE_KEY.public_key()


def make_token(**overrides: Any) -> str:
    claims = {
        "sub": USER_ID,
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "aal": "aal1",
        "tenant_id": TENANT_ID,
        "tenant_role": "admin",
    } | overrides
    return jwt.encode(claims, PRIVATE_KEY, algorithm="ES256")


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_verifier] = lambda: StaticKeyVerifier(ISSUER)

    @app.post("/admin-action")
    def admin_action(claims: Annotated[Claims, Depends(require_aal2)]) -> dict[str, str]:
        return {"sub": claims.sub}

    return TestClient(app)


def post_admin(client: TestClient, token: str) -> Any:
    return client.post("/admin-action", headers={"Authorization": f"Bearer {token}"})


def test_sem_token_responde_401_em_problem_json(client: TestClient) -> None:
    response = client.post("/admin-action")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "unauthorized"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"aud": "outra-audiencia"},
        {"iss": "http://atacante.test"},
    ],
    ids=["expirado", "audiencia", "emissor"],
)
def test_token_invalido_responde_401(client: TestClient, overrides: dict[str, Any]) -> None:
    assert post_admin(client, make_token(**overrides)).status_code == 401


def test_token_assinado_por_outra_chave_responde_401(client: TestClient) -> None:
    other = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(
        {"sub": USER_ID, "aud": "authenticated", "iss": ISSUER}, other, algorithm="ES256"
    )
    assert post_admin(client, token).status_code == 401


def test_aal1_em_acao_administrativa_responde_403_mfa_required(client: TestClient) -> None:
    response = post_admin(client, make_token(aal="aal1"))
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_required"


def test_aal2_passa_e_expoe_as_claims(client: TestClient) -> None:
    response = post_admin(client, make_token(aal="aal2"))
    assert response.status_code == 200
    assert response.json() == {"sub": USER_ID}
