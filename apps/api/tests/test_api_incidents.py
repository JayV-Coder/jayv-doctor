from datetime import UTC, datetime
from typing import Any

import pytest
from aid_api.core.auth import Claims, get_claims
from aid_api.incidents.repo import IncidentRepository, get_incident_repository
from aid_api.incidents.schemas import (
    Comment,
    IncidentChange,
    IncidentDetail,
    IncidentPage,
    IncidentSearch,
    NewComment,
)
from aid_api.main import create_app
from fastapi.testclient import TestClient

TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
INCIDENT = "00000000-0000-4000-8000-0000000005a1"
NOW = datetime(2026, 11, 3, tzinfo=UTC)


class FakeRepository(IncidentRepository):
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def search(
        self, claims: Claims, query: IncidentSearch, reference: str | None
    ) -> IncidentPage:
        self.calls.append(("search", (query, reference)))
        return IncidentPage(items=[], next_cursor=None, counts={"open": 3})

    async def update(self, claims: Claims, target: str, change: IncidentChange) -> IncidentDetail:
        self.calls.append(("update", change))
        raise NotImplementedError

    async def comment(self, claims: Claims, target: str, new: NewComment) -> Comment:
        self.calls.append(("comment", new))
        return Comment(id="c", author_id="u", body_md=new.body_md, mentions=[], created_at=NOW)


def client(repository: FakeRepository, role: str = "viewer") -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: Claims(
        sub="u", email=None, aal="aal1", tenant_id=TENANT_ID, tenant_role=role
    )
    app.dependency_overrides[get_incident_repository] = lambda: repository
    return TestClient(app, raise_server_exceptions=False)


def test_lista_traz_contagens_por_status() -> None:
    response = client(FakeRepository()).post("/api/v1/incidents/search", json={})
    assert response.json()["counts"] == {"open": 3}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("patch", f"/api/v1/incidents/{INCIDENT}", {"status": "investigating"}),
        ("post", f"/api/v1/incidents/{INCIDENT}/comments", {"body_md": "oi"}),
    ],
)
def test_viewer_nao_muda_nem_comenta(method: str, path: str, body: dict[str, Any]) -> None:
    repository = FakeRepository()
    response = getattr(client(repository), method)(path, json=body)
    assert response.status_code == 403
    assert repository.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"status": "resolved"},
        {"status": "resolved", "resolution_note": "  "},
        {},
        {"status": None},
        {"status": "talvez"},
    ],
)
def test_mudanca_invalida_responde_422(body: dict[str, Any]) -> None:
    repository = FakeRepository()
    response = client(repository, "analyst").patch(f"/api/v1/incidents/{INCIDENT}", json=body)
    assert response.status_code == 422
    assert repository.calls == []


def test_analyst_comenta() -> None:
    repository = FakeRepository()
    response = client(repository, "analyst").post(
        f"/api/v1/incidents/{INCIDENT}/comments", json={"body_md": "Olhando o gateway"}
    )
    assert response.status_code == 201
    assert repository.calls[0][0] == "comment"
