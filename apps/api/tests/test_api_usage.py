from aid_api.core.auth import Claims, get_claims
from aid_api.core.errors import ApiError
from aid_api.ingestion.repo import ERRORS as INGESTION
from aid_api.main import create_app
from aid_api.usage.repo import UsageRepository, get_usage_repository
from aid_api.usage.schemas import LlmUsage, ResourceUsage, Usage
from fastapi.testclient import TestClient

TENANT_ID = "00000000-0000-4000-8000-00000000ac01"


class FakeRepository(UsageRepository):
    async def usage(self, claims: Claims) -> Usage:
        return Usage(
            plan="pilot",
            resources=[
                ResourceUsage(
                    resource="diagnoses_llm", period="month", used=910, quota=1000, ratio=0.91
                )
            ],
            llm=LlmUsage(input_tokens=41_200_000, output_tokens=900_000, cost_estimate=None),
        )


def test_todo_papel_ve_o_uso() -> None:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: Claims(
        sub="u", email=None, aal="aal1", tenant_id=TENANT_ID, tenant_role="viewer"
    )
    app.dependency_overrides[get_usage_repository] = FakeRepository
    response = TestClient(app, headers={"authorization": "Bearer jwt"}).get("/api/v1/usage")
    assert response.status_code == 200
    assert response.json()["resources"][0]["ratio"] == 0.91


def test_cota_de_eventos_esgotada_vira_429_na_ingestao() -> None:
    error: ApiError = INGESTION["DR050"]()
    assert (error.status, error.code) == (429, "quota_exceeded")
