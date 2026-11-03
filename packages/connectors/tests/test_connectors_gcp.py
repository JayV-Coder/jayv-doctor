"""Conector do Google Cloud Logging com respostas gravadas da API (tests/fixtures/gcp)."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from aid_connectors.base import Batch, ConnectorError, Secret
from aid_connectors.gcp.auth import Endpoints
from aid_connectors.gcp.connector import GcpLoggingConnector
from aid_connectors.testing import ConnectorContractTests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

FIXTURES = Path(__file__).parent / "fixtures" / "gcp"
NOW = datetime(2026, 11, 2, 14, 10, tzinfo=UTC)
CONFIG = {"project_id": "acme-integracoes", "auth": "key", "requests_per_minute": 600}


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def service_account_key() -> str:
    """Chave de Service Account de teste, gerada na hora: nunca uma chave real no repositório."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return json.dumps(
        {
            "type": "service_account",
            "client_email": "doctor-reader@acme-integracoes.iam.gserviceaccount.com",
            "private_key": pem,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )


KEY = service_account_key()


class Recorder:
    """Transporte que responde pelas fixtures e guarda os pedidos feitos."""

    def __init__(self, pages: list[Any] | None = None, status: int = 200) -> None:
        self.pages = (
            pages
            if pages is not None
            else [
                fixture("entries-page-1.json"),
                fixture("entries-page-2.json"),
            ]
        )
        self.status = status
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "token-curto", "expires_in": 3600})
        body = json.loads(request.content)
        self.requests.append(body)
        if self.status != 200:
            name = "permission-denied.json" if self.status == 403 else "resource-exhausted.json"
            return httpx.Response(self.status, json=fixture(name))
        index = 0 if "pageToken" not in body else 1
        return httpx.Response(200, json=self.pages[index] if index < len(self.pages) else {})


def connector(recorder: Recorder) -> GcpLoggingConnector:
    return GcpLoggingConnector(
        transport=httpx.MockTransport(recorder), clock=lambda: NOW, sleep=lambda _: asyncio.sleep(0)
    )


def collect(
    recorder: Recorder, config: dict[str, Any] | None = None, checkpoint: Any = None
) -> list[Batch]:
    async def gather() -> list[Batch]:
        return [
            batch
            async for batch in connector(recorder).collect(
                Secret(KEY), config or CONFIG, checkpoint
            )
        ]

    return asyncio.run(gather())


def test_mapeia_a_entrada_do_logging_para_o_contrato() -> None:
    first = collect(Recorder())[0].events[0]
    assert first["timestamp"] == "2026-11-02T14:05:00.123456+00:00"
    assert first["severity"] == "ERROR"
    assert first["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert first["execution_id"] == "exec-981"
    assert first["source"] == {
        "provider": "gcp",
        "service": "orders-sync",
        "resource": "cloud_run_revision",
    }
    assert first["operation"] == "create_order"
    assert first["error"] == {
        "category": "TIMEOUT",
        "http_status": 504,
        "message": "Timeout ao chamar BAPI_SALESORDER_CREATEFROMDAT2",
    }
    assert first["attributes"]["pedido"] == "4500012345"


def test_execution_id_tambem_vem_do_json_payload_e_429_vira_rate_limit() -> None:
    last = collect(Recorder())[1].events[0]
    assert last["execution_id"] == "exec-982"
    assert last["severity"] == "CRITICAL"
    assert last["error"]["category"] == "RATE_LIMIT"


def test_filtro_janela_ordem_e_paginacao() -> None:
    recorder = Recorder()
    collect(recorder, {**CONFIG, "services": ["orders-sync"], "min_severity": "WARNING"})
    first, second = recorder.requests
    assert first["resourceNames"] == ["projects/acme-integracoes"]
    assert first["orderBy"] == "timestamp asc"
    assert 'timestamp >= "2026-11-01T14:10:00Z"' in first["filter"]
    assert 'timestamp < "2026-11-02T14:09:30Z"' in first["filter"]
    assert 'resource.labels.service_name=("orders-sync")' in first["filter"]
    assert "severity >= WARNING" in first["filter"]
    assert second["pageToken"] == "pagina-2"


def test_retoma_trinta_segundos_antes_do_checkpoint() -> None:
    recorder = Recorder(pages=[{}])
    collect(recorder, checkpoint={"timestamp": "2026-11-02T14:06:00Z", "insert_id": "g7h8i9"})
    assert 'timestamp >= "2026-11-02T14:05:30Z"' in recorder.requests[0]["filter"]


def test_checkpoint_avanca_e_termina_no_fim_da_janela() -> None:
    batches = collect(Recorder())
    assert batches[0].checkpoint["timestamp"] == "2026-11-02T14:05:01Z"
    assert batches[0].checkpoint["insert_id"] == "d4e5f6"
    assert batches[-1].events == []
    assert batches[-1].checkpoint["timestamp"] == "2026-11-02T14:09:30Z"


def test_event_id_estavel_para_a_mesma_entrada() -> None:
    first = [event["event_id"] for batch in collect(Recorder()) for event in batch.events]
    again = [event["event_id"] for batch in collect(Recorder()) for event in batch.events]
    assert first == again


def test_consulta_avancada_e_backfill_de_7_dias() -> None:
    recorder = Recorder(pages=[{}])
    collect(recorder, {**CONFIG, "filter": 'jsonPayload.app="orders"', "backfill_hours": 168})
    request = recorder.requests[0]["filter"]
    assert '(jsonPayload.app="orders")' in request
    assert 'timestamp >= "2026-10-26T14:10:00Z"' in request


def test_cota_estourada_vira_rate_limit_com_espera() -> None:
    with pytest.raises(ConnectorError) as raised:
        collect(Recorder(status=429))
    assert raised.value.kind == "rate_limit"
    assert raised.value.retry_after == 60


def test_sem_logging_viewer_o_teste_diz_qual_permissao_falta() -> None:
    result = asyncio.run(connector(Recorder(status=403)).test_connection(Secret(KEY), CONFIG))
    assert not result.ok
    assert "logging.logEntries.list" in result.message
    assert "roles/logging.viewer" in result.message
    assert "doctor-reader@acme-integracoes.iam.gserviceaccount.com" in result.message
    assert "acme-integracoes" in result.message


def test_credencial_que_nao_e_json_de_service_account() -> None:
    result = asyncio.run(connector(Recorder()).test_connection(Secret("nao-e-json"), CONFIG))
    assert not result.ok
    assert "Service Account" in result.message


@pytest.mark.parametrize(
    "config",
    [
        {"auth": "key"},
        {**CONFIG, "project_id": "X"},
        {**CONFIG, "min_severity": "BARULHO"},
        {**CONFIG, "backfill_hours": 12},
        {**CONFIG, "auth": "impersonation", "service_account": "x@b-proj.iam.gserviceaccount.com"},
        {**CONFIG, "filter": 'severity=ERROR) OR (timestamp>="1970-01-01T00:00:00Z"'},
        {**CONFIG, "requests_per_minute": 0},
    ],
)
def test_config_invalida(config: dict[str, Any]) -> None:
    assert GcpLoggingConnector().validate_config(config)


def test_respeita_a_cota_entre_paginas() -> None:
    waits: list[float] = []

    async def record(seconds: float) -> None:
        waits.append(seconds)

    recorder = Recorder()
    gcp = GcpLoggingConnector(
        transport=httpx.MockTransport(recorder), clock=lambda: NOW, sleep=record
    )

    async def run() -> None:
        async for _ in gcp.collect(Secret(KEY), {**CONFIG, "requests_per_minute": 60}, None):
            pass

    asyncio.run(run())
    assert waits == [1.0]


class TestGcpContract(ConnectorContractTests):
    def make_connector(self) -> GcpLoggingConnector:
        return connector(Recorder())

    def valid_config(self) -> dict[str, Any]:
        return CONFIG

    def invalid_config(self) -> dict[str, Any]:
        return {"project_id": "x"}

    def secret(self) -> str:
        return KEY

    def test_retomar_do_checkpoint_nao_repete_eventos(self) -> None:
        # O GCP repete de propósito a janela de 30 s antes do Checkpoint (entradas atrasadas); a
        # deduplicação por event_id na ingestão descarta as repetidas.
        pytest.skip("sobreposição intencional, coberta pela deduplicação do #12")


def test_filtro_com_parenteses_entre_aspas_e_aceito() -> None:
    config = {**CONFIG, "filter": 'jsonPayload.msg="falhou (timeout)"'}
    assert GcpLoggingConnector().validate_config(config) == {}


def test_token_uri_do_json_e_ignorado() -> None:
    info = json.loads(KEY)
    info["token_uri"] = "http://10.0.0.5:8080/interno"  # noqa: S105
    hosts: list[str] = []
    recorder = Recorder(pages=[{}])

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return recorder(request)

    gcp = GcpLoggingConnector(transport=httpx.MockTransport(handler), clock=lambda: NOW)
    asyncio.run(gcp.test_connection(Secret(json.dumps(info)), CONFIG))
    assert "10.0.0.5" not in hosts
    assert hosts[0] == "oauth2.googleapis.com"


def test_falha_de_rede_no_token_e_temporaria() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns")

    gcp = GcpLoggingConnector(transport=httpx.MockTransport(handler), clock=lambda: NOW)

    async def run() -> None:
        async for _ in gcp.collect(Secret(KEY), CONFIG, None):
            pass

    with pytest.raises(ConnectorError) as raised:
        asyncio.run(run())
    assert raised.value.kind == "transient"


def test_api_desativada_tem_mensagem_propria() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": 403,
                    "message": "Cloud Logging API has not been used in project 1 before",
                    "details": [{"reason": "SERVICE_DISABLED"}],
                }
            },
        )

    gcp = GcpLoggingConnector(transport=httpx.MockTransport(handler), clock=lambda: NOW)
    result = asyncio.run(gcp.test_connection(Secret(KEY), CONFIG))
    assert "desativada" in result.message
    assert "roles/logging.viewer" not in result.message


def test_mensagem_que_nao_e_texto_nao_derruba_a_coleta() -> None:
    from aid_connectors.gcp.mapping import to_event

    event = to_event(
        {
            "timestamp": "2026-11-02T14:05:00Z",
            "severity": "ERROR",
            "jsonPayload": {"message": {"code": 504}},
        }
    )
    assert event["error"]["message"] == '{"code": 504}'


def test_entradas_sem_insert_id_no_mesmo_instante_tem_ids_diferentes() -> None:
    from aid_connectors.gcp.mapping import to_event

    first = to_event({"timestamp": "2026-11-02T14:05:00Z", "textPayload": "a"})
    second = to_event({"timestamp": "2026-11-02T14:05:00Z", "textPayload": "b"})
    assert first["event_id"] != second["event_id"]


def test_token_e_reaproveitado_entre_tentativas() -> None:
    tokens = 0
    recorder = Recorder(pages=[{}])

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal tokens
        if request.url.host == "oauth2.googleapis.com":
            tokens += 1
        return recorder(request)

    gcp = GcpLoggingConnector(
        transport=httpx.MockTransport(handler), clock=lambda: NOW, sleep=lambda _: asyncio.sleep(0)
    )

    async def twice() -> None:
        for _ in range(2):
            async for _ in gcp.collect(Secret(KEY), CONFIG, None):
                pass

    asyncio.run(twice())
    assert tokens == 1


def preview(recorder: Recorder) -> Any:
    return asyncio.run(connector(recorder).test_connection(Secret(KEY), CONFIG, preview=True))


def test_teste_de_conexao_previa_quantos_registros_da_ultima_hora_atendem_aos_filtros() -> None:
    recorder = Recorder(pages=[{"entries": [{"insertId": str(n)} for n in range(48)]}])
    result = preview(recorder)
    assert result.ok
    assert "48 registros na última hora" in result.message
    assert 'timestamp >= "2026-11-02T13:10:00Z"' in recorder.requests[0]["filter"]
    assert recorder.requests[0]["pageSize"] == 1000


def test_previa_com_mais_paginas_diz_pelo_menos() -> None:
    page = {"entries": [{"insertId": "a"}] * 1000, "nextPageToken": "pagina-2"}
    assert "Mais de 1.000 registros na última hora" in preview(Recorder(pages=[page])).message


def test_pagina_vazia_com_continuacao_nao_inventa_contagem() -> None:
    result = preview(Recorder(pages=[{"nextPageToken": "x"}]))
    assert result.ok
    assert "atendem aos filtros" not in result.message
    assert "Não deu para contar" in result.message


def test_teste_sem_previa_le_so_uma_entrada() -> None:
    recorder = Recorder(pages=[{"entries": [{"insertId": "a"}]}])
    result = asyncio.run(connector(recorder).test_connection(Secret(KEY), CONFIG))
    assert result.ok
    assert recorder.requests[0]["pageSize"] == 1
    assert "registros" not in result.message


@pytest.mark.parametrize(
    "url", ["https://exemplo.com/token", "http://10.0.0.5/token", "http://localhost.evil.com/t"]
)
def test_endpoints_trocados_so_aceitam_loopback(url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        Endpoints.from_environment({"AID_GCP_OAUTH_URL": url})


def test_endpoints_do_e2e_e_padrao_do_google() -> None:
    assert Endpoints.from_environment({}).oauth == "https://oauth2.googleapis.com/token"
    local = Endpoints.from_environment(
        {
            "AID_GCP_OAUTH_URL": "http://127.0.0.1:8095/token",
            "AID_GCP_LOGGING_URL": "http://127.0.0.1:8095/v2/entries:list",
        }
    )
    assert local.logging == "http://127.0.0.1:8095/v2/entries:list"
