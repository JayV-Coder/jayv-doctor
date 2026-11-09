import json
from datetime import UTC, datetime
from typing import Any

import pytest
from aid_api.connectors.repo import ConnectorRepository, get_connector_repository
from aid_api.connectors.schemas import Connector, ConnectorChange, ConnectorSync, NewConnector
from aid_api.core.auth import Claims, get_claims
from aid_api.core.errors import ApiError
from aid_api.main import create_app
from fastapi.testclient import TestClient

TENANT_ID = "00000000-0000-4000-8000-00000000ac01"
INTEGRATION_ID = "00000000-0000-4000-8000-0000000001a1"
CONNECTOR_ID = "00000000-0000-4000-8000-0000000000c1"
CREDENTIAL = "credencial-super-secreta-do-cliente"


def connector(**overrides: Any) -> Connector:
    data: dict[str, Any] = {
        "id": CONNECTOR_ID,
        "integration_id": INTEGRATION_ID,
        "provider": "fake",
        "name": "Fake",
        "config": {"pages": 1},
        "status": "active",
        "paused_reason": None,
        "consecutive_failures": 0,
        "checkpoint": None,
        "last_sync_records": None,
        "sync_interval_seconds": 300,
        "last_sync_at": None,
        "last_error": None,
        "next_run_at": datetime(2026, 11, 3, tzinfo=UTC),
        "created_at": datetime(2026, 11, 3, tzinfo=UTC),
        **overrides,
    }
    return Connector.model_validate(data)


class FakeRepository(ConnectorRepository):
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def all(self, claims: Claims) -> list[Connector]:
        return [connector()]

    async def get(self, claims: Claims, target: str) -> Connector:
        if target != CONNECTOR_ID:
            raise ApiError(404, "not_found", "Conector não encontrado.")
        return connector()

    async def create(self, claims: Claims, new: NewConnector) -> Connector:
        self.calls.append(("create", new))
        return connector(name=new.name)

    async def update(
        self, claims: Claims, target: str, change: ConnectorChange, check_config: Any
    ) -> Connector:
        if change.config is not None:
            check_config("fake", change.config)
        self.calls.append(("update", change))
        return connector()

    async def action(self, claims: Claims, target: str, name: str) -> None:
        self.calls.append((name, target))

    async def syncs(self, claims: Claims, target: str) -> list[ConnectorSync]:
        return []


def claims(role: str, aal: str = "aal2") -> Claims:
    return Claims(sub="u", email=None, aal=aal, tenant_id=TENANT_ID, tenant_role=role)


def client(
    role: str = "admin", repository: FakeRepository | None = None, aal: str = "aal2"
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_claims] = lambda: claims(role, aal)
    app.dependency_overrides[get_connector_repository] = lambda: repository or FakeRepository()
    return TestClient(app)


NEW = {
    "integration_id": INTEGRATION_ID,
    "provider": "fake",
    "name": "Fake de teste",
    "config": {"pages": 2},
    "credential": CREDENTIAL,
}


def test_criar_nunca_devolve_a_credencial() -> None:
    repository = FakeRepository()
    response = client(repository=repository).post("/api/v1/connectors", json=NEW)
    assert response.status_code == 201
    assert CREDENTIAL not in response.text
    assert "credential" not in response.json()
    assert "secret" not in json.dumps(response.json())


def test_get_e_lista_nunca_trazem_a_credencial_nem_mascarada() -> None:
    for path in ("/api/v1/connectors", f"/api/v1/connectors/{CONNECTOR_ID}"):
        body = client("viewer").get(path).text
        assert "credential" not in body
        assert "secret" not in body
        assert "***" not in body


def test_config_invalida_para_o_provedor_vira_422_sem_ecoar_valores() -> None:
    response = client().post("/api/v1/connectors", json={**NEW, "config": {"pages": -5}})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_config"
    assert "-5" not in response.text


def test_provedor_sem_conector_neste_ambiente_vira_422() -> None:
    response = client().post("/api/v1/connectors", json={**NEW, "provider": "sap"})
    assert response.status_code == 422
    assert response.json()["code"] == "provider_unavailable"


@pytest.mark.parametrize(
    ("role", "aal"), [("analyst", "aal2"), ("viewer", "aal2"), ("admin", "aal1")]
)
def test_so_owner_e_admin_com_mfa_gerenciam(role: str, aal: str) -> None:
    response = client(role, aal=aal).post("/api/v1/connectors", json=NEW)
    assert response.status_code == 403


def test_teste_de_conexao_antes_de_salvar_nao_guarda_nada() -> None:
    repository = FakeRepository()
    response = client(repository=repository).post(
        "/api/v1/connectors/test",
        json={"provider": "fake", "config": {"pages": 1}, "credential": CREDENTIAL},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "message": "Conexão estabelecida.", "capabilities": {}}
    assert repository.calls == []


def test_teste_de_conexao_recusado_explica_sem_a_credencial() -> None:
    response = client().post(
        "/api/v1/connectors/test",
        json={
            "provider": "fake",
            "config": {"pages": 1, "fail": {"page": 1, "kind": "auth"}},
            "credential": CREDENTIAL,
        },
    )
    assert response.json()["ok"] is False
    assert CREDENTIAL not in response.text


def test_teste_de_conector_salvo_usa_a_config_salva_e_a_credencial_do_corpo() -> None:
    response = client().post(
        f"/api/v1/connectors/{CONNECTOR_ID}/test", json={"credential": CREDENTIAL}
    )
    assert response.json()["ok"] is True


@pytest.mark.parametrize("action", ["sync", "pause", "resume"])
def test_acoes(action: str) -> None:
    repository = FakeRepository()
    response = client(repository=repository).post(f"/api/v1/connectors/{CONNECTOR_ID}/{action}")
    assert response.status_code == (202 if action == "sync" else 204)
    assert repository.calls == [(action, CONNECTOR_ID)]


def test_patch_com_credencial_troca_no_vault_e_nao_ecoa() -> None:
    repository = FakeRepository()
    response = client(repository=repository).patch(
        f"/api/v1/connectors/{CONNECTOR_ID}", json={"credential": "nova-credencial-x"}
    )
    assert response.status_code == 200
    assert "nova-credencial-x" not in response.text
    change = repository.calls[0][1]
    assert change.credential is not None


def test_lista_de_sincronizacoes_para_todo_papel() -> None:
    response = client("viewer").get(f"/api/v1/connectors/{CONNECTOR_ID}/syncs")
    assert response.status_code == 200


def test_credencial_e_guardada_como_veio_inclusive_com_quebra_de_linha() -> None:
    repository = FakeRepository()
    pem = "-----BEGIN KEY-----\nabc\n-----END KEY-----\n"
    client(repository=repository).post(
        "/api/v1/connectors", json={**NEW, "credential": pem, "name": "  Fake  "}
    )
    created = repository.calls[0][1]
    assert created.credential.get_secret_value() == pem
    assert created.name == "Fake"


def test_patch_so_com_nulos_e_recusado() -> None:
    response = client().patch(f"/api/v1/connectors/{CONNECTOR_ID}", json={"name": None})
    assert response.status_code == 422


def test_config_de_falha_malformada_e_recusada_e_nao_vira_500() -> None:
    response = client().post(
        "/api/v1/connectors/test",
        json={"provider": "fake", "config": {"pages": 1, "fail": "x"}, "credential": "c"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_config"


def test_patch_de_config_invalida_vira_422() -> None:
    response = client().patch(f"/api/v1/connectors/{CONNECTOR_ID}", json={"config": {"pages": -1}})
    assert response.status_code == 422


def test_criar_aceita_o_intervalo_de_sincronizacao() -> None:
    repository = FakeRepository()
    client(repository=repository).post(
        "/api/v1/connectors", json={**NEW, "sync_interval_seconds": 60}
    )
    assert repository.calls[0][1].sync_interval_seconds == 60
    response = client().post("/api/v1/connectors", json={**NEW, "sync_interval_seconds": 10})
    assert response.status_code == 422


class SpyConnector:
    def __init__(self) -> None:
        self.previews: list[bool] = []

    def validate_config(self, config: Any) -> dict[str, str]:
        return {}

    async def test_connection(self, secret: Any, config: Any, *, preview: bool = False) -> Any:
        from aid_connectors.base import TestResult

        self.previews.append(preview)
        return TestResult(True, "ok")


def test_previa_so_no_teste_antes_de_salvar(monkeypatch: pytest.MonkeyPatch) -> None:
    from aid_api.connectors import service

    spy = SpyConnector()
    monkeypatch.setattr(service, "implementation", lambda provider: spy)
    api = client()
    api.post("/api/v1/connectors/test", json={"provider": "fake", "credential": "c"})
    api.post(f"/api/v1/connectors/{CONNECTOR_ID}/test", json={"credential": "c"})
    assert spy.previews == [True, False]


def test_teste_do_salesforce_mostra_as_fontes_da_edicao(monkeypatch: pytest.MonkeyPatch) -> None:
    from aid_api.connectors import service
    from aid_connectors.base import TestResult

    class EditionWithoutEventMonitoring(SpyConnector):
        async def test_connection(self, secret: Any, config: Any, *, preview: bool = False) -> Any:
            return TestResult(
                True,
                "Conexão estabelecida. Fontes: ApexLog. EventLogFile indisponível nesta edição.",
                {"apex_log": True, "event_log_file": False},
            )

    monkeypatch.setattr(service, "implementation", lambda provider: EditionWithoutEventMonitoring())
    response = client().post(
        "/api/v1/connectors/test",
        json={"provider": "salesforce", "config": {"sources": ["apex_log"]}, "credential": "c"},
    )
    body = response.json()
    assert body["capabilities"] == {"apex_log": True, "event_log_file": False}
    assert "EventLogFile indisponível nesta edição" in body["message"]
