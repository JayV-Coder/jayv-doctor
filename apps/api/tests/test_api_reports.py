"""Rotas do Relatório técnico (ticket #32), com repositório e Storage falsos."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import ClassVar

from aid_api.core.auth import Claims, get_claims
from aid_api.core.storage import Storage, get_storage
from aid_api.core.tokens import token_hash
from aid_api.main import create_app
from aid_api.reports.repo import ReportRepository, SharedFile, get_report_repository
from aid_api.reports.schemas import ReportQueued, ReportRequest, ReportSummary
from fastapi.testclient import TestClient

TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
REPORT = "00000000-0000-4000-8000-0000000007a1"
INCIDENT = "00000000-0000-4000-8000-0000000005a1"
NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
SUMMARY = ReportSummary(
    id=REPORT,
    incident_id=INCIDENT,
    diagnosis_id=None,
    diagnosis_version=None,
    format="pdf",
    include_timeline=True,
    include_event_excerpts=False,
    status="ready",
    size_bytes=10,
    content_sha256="c" * 64,
    error=None,
    created_at=NOW,
    completed_at=NOW,
    shares=[],
)


class FakeRepository(ReportRepository):
    shared: ClassVar[dict[str, str]] = {}
    requests: ClassVar[list[tuple[str, ReportRequest]]] = []
    accessed: ClassVar[list[str]] = []

    async def request(
        self, claims: Claims, incident: str, body: ReportRequest, key: str
    ) -> ReportQueued:
        self.requests.append((incident, body))
        return ReportQueued(report_id=REPORT, status="queued")

    async def detail(
        self, claims: Claims, target: str, sign: Callable[[str], Awaitable[str]]
    ) -> tuple[ReportSummary, str | None]:
        return SUMMARY, await sign(f"{TENANT_ID}/{REPORT}.pdf")

    async def ready_path(self, claims: Claims, target: str) -> str:
        return f"{TENANT_ID}/{REPORT}.pdf"

    async def share(
        self, claims: Claims, target: str, token: str, download_url: str
    ) -> tuple[str, datetime]:
        self.shared[token_hash(token)] = download_url
        return "share-1", NOW

    async def record_access(self, token: str) -> None:
        self.accessed.append(token)

    async def open_shared(self, token: str) -> SharedFile | None:
        url = self.shared.get(token_hash(token))
        return SharedFile(url, "pdf", "inc-0142.pdf") if url else None


class FakeStorage(Storage):
    signed: ClassVar[list[tuple[str, int, str]]] = []

    async def sign_download(
        self, token: str, path: str, seconds: int, bucket: str = "doctor-raw-logs"
    ) -> str:
        self.signed.append((path, seconds, bucket))
        return f"https://storage.test/sign/{bucket}/{path}?t={seconds}"

    async def fetch(self, signed_url: str) -> bytes | None:
        return b"%PDF-1.7 teste"


def client(role: str) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: Claims(
        sub="u", email=None, aal="aal1", tenant_id=TENANT_ID, tenant_role=role
    )
    app.dependency_overrides[get_report_repository] = FakeRepository
    app.dependency_overrides[get_storage] = FakeStorage
    return TestClient(app, headers={"authorization": "Bearer jwt"})


def test_analyst_pede_e_o_viewer_nao() -> None:
    body = {"format": "md", "include_timeline": True}
    response = client("analyst").post(f"/api/v1/incidents/{INCIDENT}/reports", json=body)
    assert response.status_code == 202
    assert response.json() == {"report_id": REPORT, "status": "queued"}
    assert FakeRepository.requests[-1][1].format == "md"
    denied = client("viewer").post(f"/api/v1/incidents/{INCIDENT}/reports", json=body)
    assert denied.status_code == 403


def test_viewer_baixa_por_url_assinada_de_5_minutos_no_bucket_dos_relatorios() -> None:
    response = client("viewer").get(f"/api/v1/reports/{REPORT}")
    assert response.status_code == 200
    assert response.json()["expires_in"] == 300
    assert FakeStorage.signed[-1] == (f"{TENANT_ID}/{REPORT}.pdf", 300, "doctor-reports")


def test_link_compartilhado_abre_sem_sessao_pelo_proxy() -> None:
    created = client("analyst").post(f"/api/v1/reports/{REPORT}/shares")
    assert created.status_code == 201
    url = created.json()["url"]
    assert "/compartilhado#" in url
    token = url.split("#", 1)[1]
    assert FakeStorage.signed[-1][1] == 7 * 24 * 3600

    anonymous = TestClient(create_app())
    anonymous.app.dependency_overrides[get_report_repository] = FakeRepository  # type: ignore[attr-defined]
    anonymous.app.dependency_overrides[get_storage] = FakeStorage  # type: ignore[attr-defined]
    opened = anonymous.post("/api/v1/shared-reports", json={"token": token})
    assert opened.status_code == 200
    assert opened.content.startswith(b"%PDF")
    assert opened.headers["content-disposition"] == 'attachment; filename="inc-0142.pdf"'
    assert "storage.test" not in opened.text
    assert FakeRepository.accessed == [token]
    wrong = anonymous.post("/api/v1/shared-reports", json={"token": "x" * 43})
    assert wrong.status_code == 404
    assert FakeRepository.accessed == [token]
