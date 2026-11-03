from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aid_api.core.auth import Claims, get_claims
from aid_api.core.idempotency import (
    IdempotencySession,
    IdempotencyStore,
    Stored,
    get_idempotency_store,
)
from aid_api.diagnoses.repo import DiagnosisRepository, get_diagnosis_repository
from aid_api.diagnoses.router import processing_key
from aid_api.diagnoses.schemas import (
    DiagnosisDetail,
    DiagnosisQueued,
    DiagnosisRequest,
    DiagnosisSettings,
)
from aid_api.main import create_app
from fastapi.testclient import TestClient

TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
INCIDENT = "00000000-0000-4000-8000-0000000005a1"
DIAGNOSIS = "00000000-0000-4000-8000-0000000009a1"


class FakeRepository(DiagnosisRepository):
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def request(
        self, claims: Claims, incident: str, body: DiagnosisRequest, key: str
    ) -> DiagnosisQueued:
        self.calls.append(("request", (incident, body.mode, body.include_knowledge_base, key)))
        return DiagnosisQueued(diagnosis_id=DIAGNOSIS, status="queued", version=1)

    async def detail(self, claims: Claims, target: str) -> DiagnosisDetail:
        return DiagnosisDetail.model_validate(
            {
                "id": target,
                "incident_id": INCIDENT,
                "version": 1,
                "status": "inconclusive",
                "stage": "done",
                "requested_mode": "hybrid",
                "mode": "hybrid",
                "classification": "UPSTREAM_TIMEOUT",
                "confidence": 0.68,
                "requires_human_review": True,
                "created_at": "2026-11-02T14:00:00Z",
                "published_at": "2026-11-02T14:00:20Z",
                "probable_cause": "O SAP não respondeu.",
                "responsible_system": None,
                "include_knowledge_base": True,
                "verification_notes": [],
                "provider": "anthropic",
                "model": "claude-sonnet-5-5",
                "ruleset_version": "2026.10.1",
                "input_tokens": 10,
                "output_tokens": 5,
                "duration_ms": 20000,
                "error": None,
                "hypotheses": [],
                "evidence": [
                    {
                        "rank": 1,
                        "kind": "rule_match",
                        "ref_id": None,
                        "event_timestamp": None,
                        "label": "INT-003",
                        "finding": "504",
                        "event_id": None,
                        "execution_id": None,
                    }
                ],
                "recommendations": [],
                "feedback": [],
            }
        )

    async def update_settings(self, claims: Claims, new: DiagnosisSettings) -> DiagnosisSettings:
        self.calls.append(("settings", new.auto_diagnose_critical))
        return new


class FreshKeys(IdempotencySession, IdempotencyStore):
    """Toda chave é nova: o replay da resposta é testado em test_api_platform."""

    async def reserve(self, key: str, request_hash: str) -> Stored | None:
        return None

    async def remember(self, key: str, status: int, body: str) -> None:
        return None

    @asynccontextmanager
    async def session(self, claims: Claims) -> AsyncIterator[IdempotencySession]:
        yield self


def client(repository: FakeRepository, role: str, aal: str = "aal2") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: Claims(
        sub="u", email=None, aal=aal, tenant_id=TENANT_ID, tenant_role=role
    )
    app.dependency_overrides[get_diagnosis_repository] = lambda: repository
    app.dependency_overrides[get_idempotency_store] = lambda: FreshKeys()
    return TestClient(app, headers={"authorization": "Bearer jwt"})


def test_pedir_responde_202_e_a_chave_vira_processing_key() -> None:
    repository = FakeRepository()
    response = client(repository, "analyst").post(
        f"/api/v1/incidents/{INCIDENT}/diagnoses",
        json={"mode": "rules_only", "include_knowledge_base": False},
        headers={"Idempotency-Key": "abc-123"},
    )
    assert response.status_code == 202
    assert response.json() == {"diagnosis_id": DIAGNOSIS, "status": "queued", "version": 1}
    incident, mode, knowledge, key = repository.calls[0][1]
    assert (incident, mode, knowledge) == (INCIDENT, "rules_only", False)
    # Mesma requisição, mesma chave no banco; outro corpo ou outro Usuário, outra chave.
    body = DiagnosisRequest(mode="rules_only", include_knowledge_base=False)
    analyst = Claims(sub="u", email=None, aal="aal2", tenant_id=TENANT_ID, tenant_role="analyst")
    assert key == processing_key(analyst, INCIDENT, body, "abc-123")
    assert key != processing_key(analyst, INCIDENT, DiagnosisRequest(), "abc-123")
    other = Claims(sub="v", email=None, aal="aal2", tenant_id=TENANT_ID, tenant_role="analyst")
    assert key != processing_key(other, INCIDENT, body, "abc-123")
    assert len(processing_key(analyst, INCIDENT, body, "x" * 255)) == 68


def test_padrao_e_hibrido_com_base_e_sem_chave_gera_uma() -> None:
    repository = FakeRepository()
    client(repository, "owner").post(f"/api/v1/incidents/{INCIDENT}/diagnoses", json={})
    incident, mode, knowledge, key = repository.calls[0][1]
    assert (incident, mode, knowledge) == (INCIDENT, "hybrid", True)
    assert key.startswith("req:")
    assert len(key) > len("req:")


def test_viewer_le_mas_nao_pede() -> None:
    api = client(FakeRepository(), "viewer")
    assert api.post(f"/api/v1/incidents/{INCIDENT}/diagnoses", json={}).status_code == 403
    detail = api.get(f"/api/v1/diagnoses/{DIAGNOSIS}")
    assert detail.status_code == 200
    assert detail.json()["confidence"] == 0.68


def test_modo_invalido() -> None:
    response = client(FakeRepository(), "analyst").post(
        f"/api/v1/incidents/{INCIDENT}/diagnoses", json={"mode": "automatico"}
    )
    assert response.status_code == 422


def test_so_owner_e_admin_ligam_o_automatico() -> None:
    body = {"auto_diagnose_critical": True}
    assert (
        client(FakeRepository(), "analyst").put("/api/v1/settings/diagnosis", json=body).status_code
        == 403
    )
    without_mfa = client(FakeRepository(), "admin", aal="aal1").put(
        "/api/v1/settings/diagnosis", json=body
    )
    assert without_mfa.status_code == 403
    repository = FakeRepository()
    assert client(repository, "admin").put("/api/v1/settings/diagnosis", json=body).json() == body
    assert repository.calls == [("settings", True)]


def test_corrigir_exige_o_que_e_certo_e_viewer_nao_revisa() -> None:
    url = f"/api/v1/diagnoses/{DIAGNOSIS}/feedback"
    analyst = client(FakeRepository(), "analyst")
    assert analyst.post(url, json={"verdict": "corrected", "comment": "x"}).status_code == 422
    assert analyst.post(url, json={"verdict": "accepted", "nota": 1}).status_code == 422
    assert client(FakeRepository(), "viewer").post(
        url, json={"verdict": "accepted"}
    ).status_code == (403)
    assert (
        client(FakeRepository(), "viewer")
        .post(f"/api/v1/incidents/{INCIDENT}/knowledge")
        .status_code
        == 403
    )
