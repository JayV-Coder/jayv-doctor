import hashlib
import json
from typing import Any

import pytest
from aid_api.core.auth import Claims, get_claims
from aid_api.core.errors import ApiError
from aid_api.ingestion.repo import (
    IngestionRepository,
    TokenIdentity,
    get_ingestion_repository,
    invalid_token,
)
from aid_api.ingestion.schemas import IngestionToken
from aid_api.main import create_app
from fastapi.testclient import TestClient

USER_ID = "00000000-0000-4000-8000-0000000a0001"
TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
INTEGRATION_ID = "00000000-0000-4000-8000-0000000001a1"
CREDENTIAL_ID = "00000000-0000-4000-8000-0000000000f1"
TOKEN = "aid_ing_" + "A" * 43


def event(**overrides: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "event_id": "0190f3a1-7b2c-7d4e-8f00-123456789abc",
        "integration_id": INTEGRATION_ID,
        "timestamp": "2026-11-02T14:05:00Z",
        "source": {"provider": "sap", "service": "PI"},
        "operation": "BAPI_SALESORDER_CREATEFROMDAT2",
        "severity": "ERROR",
        **overrides,
    }


class FakeRepository(IngestionRepository):
    def __init__(self, error: ApiError | None = None) -> None:
        self.error = error
        self.accepted: list[dict[str, Any]] | None = None
        self.token_hashes: list[str] = []
        self.created: tuple[str, str, str, str] | None = None

    async def identify(self, token_hash: str) -> TokenIdentity:
        self.token_hashes.append(token_hash)
        if self.error:
            raise self.error
        return TokenIdentity(
            token_id=CREDENTIAL_ID, tenant_id=TENANT_ID, integration_id=INTEGRATION_ID
        )

    async def accept(self, token_hash: str, events: list[dict[str, Any]]) -> str:
        self.accepted = events
        return "batch-1"

    async def tokens(self, claims: Claims) -> list[IngestionToken]:
        return []

    async def create_token(
        self, claims: Claims, name: str, integration_id: str, token_hash: str, prefix: str
    ) -> str:
        self.created = (name, integration_id, token_hash, prefix)
        return CREDENTIAL_ID

    async def revoke_token(self, claims: Claims, target: str) -> None:
        return None


def client(repository: FakeRepository, identity: Claims | None = None) -> TestClient:
    app = create_app()
    if identity:
        app.dependency_overrides[get_claims] = lambda: identity
    app.dependency_overrides[get_ingestion_repository] = lambda: repository
    return TestClient(app)


def post_events(repository: FakeRepository, body: object, token: str | None = TOKEN) -> Any:
    headers = {"authorization": f"Bearer {token}"} if token else {}
    return client(repository).post(
        "/api/v1/ingestion/events", content=json.dumps(body), headers=headers
    )


def test_lote_valido_responde_202_e_grava_so_os_aceitos() -> None:
    repository = FakeRepository()
    response = post_events(
        repository,
        {"events": [event(), event(severity="NIVEL"), event(integration_id="outra")]},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] == 1
    assert [item["index"] for item in body["rejected"]] == [1, 2]
    assert body["rejected"][1]["reason"] == "integration_id não é a do token"
    assert repository.accepted == [event()]
    assert repository.token_hashes == [hashlib.sha256(TOKEN.encode()).hexdigest()]


def test_motivo_da_rejeicao_nao_ecoa_o_conteudo() -> None:
    response = post_events(FakeRepository(), {"events": [event(severity="cpf 529.982.247-25")]})
    reason = response.json()["rejected"][0]["reason"]
    assert "529" not in reason
    assert "$.severity" in reason


def test_tenant_id_no_payload_recusa_o_lote_inteiro() -> None:
    response = post_events(FakeRepository(), {"events": [event(), {**event(), "tenant_id": "x"}]})
    assert response.status_code == 422
    assert response.json()["code"] == "tenant_id_not_allowed"


@pytest.mark.parametrize("token", [None, "eyJhbGciOi.jwt.de.usuario", "aid_ing_revogado"])
def test_token_ausente_invalido_ou_revogado_responde_401(token: str | None) -> None:
    repository = FakeRepository(invalid_token())
    response = post_events(repository, {"events": [event()]}, token=token)
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_ingestion_token"


def test_mais_de_500_eventos_responde_413() -> None:
    response = post_events(FakeRepository(), {"events": [event()] * 501})
    assert response.status_code == 413


def test_mais_de_1_mb_responde_413() -> None:
    big = event(attributes={"texto": "x" * 3000})
    response = post_events(FakeRepository(), {"events": [big] * 400})
    assert response.status_code == 413
    assert response.json()["code"] == "batch_too_large"


@pytest.mark.parametrize("body", [[event()], {"events": "x"}, "nao-e-json"])
def test_corpo_fora_do_formato_responde_422(body: object) -> None:
    response = post_events(FakeRepository(), body)
    assert response.status_code == 422


def test_lote_sem_nenhum_aceito_nao_grava_nada() -> None:
    repository = FakeRepository()
    response = post_events(repository, {"events": [event(severity="x")]})
    assert response.json()["accepted"] == 0
    assert repository.accepted is None


def manager(role: str = "admin", aal: str = "aal2") -> Claims:
    return Claims(sub=USER_ID, email=None, aal=aal, tenant_id=TENANT_ID, tenant_role=role)


def test_criar_token_devolve_o_valor_uma_vez_e_guarda_so_o_hash() -> None:
    repository = FakeRepository()
    response = client(repository, manager()).post(
        "/api/v1/ingestion-tokens", json={"name": "SAP PI", "integration_id": INTEGRATION_ID}
    )
    assert response.status_code == 201
    token = response.json()["token"]
    assert token.startswith("aid_ing_")
    assert repository.created is not None
    _name, _integration, token_hash, prefix = repository.created
    assert token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token.startswith(prefix)
    assert token not in json.dumps(repository.created[:2])


@pytest.mark.parametrize(
    ("role", "aal"), [("analyst", "aal2"), ("viewer", "aal2"), ("admin", "aal1")]
)
def test_so_owner_e_admin_com_mfa_gerenciam_tokens(role: str, aal: str) -> None:
    response = client(FakeRepository(), manager(role, aal)).post(
        "/api/v1/ingestion-tokens", json={"name": "SAP PI", "integration_id": INTEGRATION_ID}
    )
    assert response.status_code == 403
