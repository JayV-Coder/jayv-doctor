from collections.abc import AsyncIterator
from datetime import UTC, datetime

from aid_api.audit.repo import AuditRepository, category_of, get_audit_repository
from aid_api.audit.schemas import AuditEntry, AuditPage, AuditSearch
from aid_api.core.auth import Claims, get_claims
from aid_api.core.request_meta import describe
from aid_api.main import create_app
from fastapi.testclient import TestClient
from starlette.requests import Request

TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
ENTRY = AuditEntry(
    id="1",
    occurred_at=datetime(2026, 11, 2, 14, 40, tzinfo=UTC),
    actor_type="user",
    actor_id="u",
    actor_label="julia@acme.test",
    action="membership.role_changed",
    category="security",
    resource_type="membership",
    resource_id="m1",
    before={"role": "analyst"},
    after={"role": "viewer"},
    ip="177.10.0.1",
)


class FakeRepository(AuditRepository):
    def __init__(self) -> None:
        self.queries: list[AuditSearch] = []

    async def search(self, claims: Claims, query: AuditSearch) -> AuditPage:
        self.queries.append(query)
        return AuditPage(items=[ENTRY], next_cursor=None)

    async def export(self, claims: Claims, query: AuditSearch) -> AsyncIterator[AuditEntry]:
        self.queries.append(query)
        yield ENTRY


def client(repository: FakeRepository, role: str, aal: str = "aal2") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: Claims(
        sub="u", email=None, aal=aal, tenant_id=TENANT_ID, tenant_role=role
    )
    app.dependency_overrides[get_audit_repository] = lambda: repository
    return TestClient(app, headers={"authorization": "Bearer jwt"})


def test_so_owner_e_admin_com_mfa_leem() -> None:
    url = "/api/v1/audit-logs/search"
    assert client(FakeRepository(), "analyst").post(url, json={}).status_code == 403
    assert client(FakeRepository(), "admin", aal="aal1").post(url, json={}).status_code == 403
    response = client(FakeRepository(), "admin").post(url, json={"category": "security"})
    assert response.status_code == 200
    assert response.json()["items"][0]["before"] == {"role": "analyst"}


def test_csv_traz_o_cabecalho_e_o_registro() -> None:
    repository = FakeRepository()
    response = client(repository, "owner").post(
        "/api/v1/audit-logs/export", json={"q": "julia@acme.test"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert (
        lines[0] == "occurred_at,actor_type,actor,action,resource_type,resource_id,before,after,ip"
    )
    assert "julia@acme.test,membership.role_changed" in lines[1]
    # O termo (um e-mail) foi no corpo, não na URL.
    assert repository.queries[0].q == "julia@acme.test"


def test_categoria_pelo_prefixo_da_acao() -> None:
    assert category_of("auth.login") == "security"
    assert category_of("vault.secret_read") == "connectors"
    assert category_of("diagnosis.reviewed") == "diagnosis"
    assert category_of("raw_log.downloaded") == "data"
    assert category_of("algo.novo") is None


def test_meta_da_requisicao_para_a_auditoria() -> None:
    scope = {
        "type": "http",
        "headers": [
            (b"x-forwarded-for", b"177.10.0.1, 10.0.0.1"),
            (b"user-agent", b"Mozilla/5.0"),
            (b"x-request-id", b"req-1"),
        ],
        "client": ("10.0.0.2", 1234),
    }
    assert describe(Request(scope)) == {
        "request_id": "req-1",
        "ip": "177.10.0.1",
        "user_agent": "Mozilla/5.0",
    }
    hostile = Request(
        {"type": "http", "headers": [(b"x-forwarded-for", b"'; drop"), (b"x-request-id", b"a b")]}
    )
    meta = describe(hostile)
    assert "ip" not in meta
    assert meta["request_id"] != "a b"
