from datetime import UTC, datetime

import pytest
from aid_api.core.auth import Claims, get_claims
from aid_api.main import create_app
from aid_api.privacy.repo import PrivacyRepository, get_privacy_repository
from aid_api.privacy.schemas import (
    DeletionRequest,
    PrivacySettings,
    Retention,
    RetentionChange,
    SubjectEvents,
)
from fastapi.testclient import TestClient

TENANT_ID = "00000000-0000-4000-8000-00000000ac01"


class FakeRepository(PrivacyRepository):
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def settings(self, claims: Claims) -> PrivacySettings:
        return PrivacySettings(
            retention=[
                Retention(data_class="raw_logs", days=30, default_days=30, min_days=7, max_days=90)
            ],
            llm_enabled=True,
            llm_provider="anthropic",
            deletion=None,
        )

    async def set_retention(self, claims: Claims, change: RetentionChange) -> None:
        self.calls.append(("retention", change.days))

    async def request_deletion(self, claims: Claims, request: DeletionRequest) -> None:
        self.calls.append(("deletion", request.confirmation))

    async def find_subject(self, claims: Claims, reference: str) -> SubjectEvents:
        self.calls.append(("subject", reference))
        return SubjectEvents(events=2, first_seen=datetime.now(UTC), last_seen=datetime.now(UTC))


def client(repository: FakeRepository, role: str, aal: str = "aal2") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: Claims(
        sub="u", email=None, aal=aal, tenant_id=TENANT_ID, tenant_role=role
    )
    app.dependency_overrides[get_privacy_repository] = lambda: repository
    return TestClient(app, headers={"authorization": "Bearer jwt"})


def test_todo_papel_ve_e_so_gestor_com_mfa_muda() -> None:
    assert client(FakeRepository(), "viewer", "aal1").get("/api/v1/privacy").status_code == 200
    body = {"data_class": "raw_logs", "days": 15}
    assert (
        client(FakeRepository(), "analyst").put("/api/v1/privacy/retention", json=body).status_code
        == 403
    )
    assert (
        client(FakeRepository(), "admin", "aal1")
        .put("/api/v1/privacy/retention", json=body)
        .status_code
        == 403
    )
    repository = FakeRepository()
    assert (
        client(repository, "admin").put("/api/v1/privacy/retention", json=body).status_code == 204
    )
    assert repository.calls == [("retention", 15)]


def test_so_owner_pede_a_exclusao_total() -> None:
    body = {"confirmation": "acme"}
    assert (
        client(FakeRepository(), "admin").post("/api/v1/privacy/deletion", json=body).status_code
        == 403
    )
    repository = FakeRepository()
    response = client(repository, "owner").post("/api/v1/privacy/deletion", json=body)
    assert response.status_code == 202
    assert repository.calls == [("deletion", "acme")]


def test_titular_pela_referencia_em_hmac(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "/api/v1/privacy/subject/search"
    monkeypatch.delenv("HMAC_MASTER_KEY", raising=False)
    assert (
        client(FakeRepository(), "admin").post(url, json={"reference": "4500012345"}).status_code
        == 503
    )
    monkeypatch.setenv("HMAC_MASTER_KEY", "chave-de-teste")
    repository = FakeRepository()
    response = client(repository, "admin").post(url, json={"reference": "4500012345"})
    assert response.json()["events"] == 2
    # O número digitado nunca chega ao banco: só o HMAC.
    assert repository.calls[0][1] != "4500012345"
    assert str(repository.calls[0][1]).startswith("hmac:")
