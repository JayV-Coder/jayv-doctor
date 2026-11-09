"""Conector do SAP Integration Suite (ticket #38, fase B) contra uma API falsa."""

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from aid_connectors.base import Secret
from aid_connectors.sap.integration_suite import SapIntegrationSuiteConnector, odata_date
from aid_connectors.testing import ConnectorContractTests

NOW = datetime(2026, 11, 10, 18, 0, tzinfo=UTC)
SECRET = json.dumps({"client_id": "sb-cpi-api", "client_secret": "segredo-da-service-key"})
CONFIG: dict[str, Any] = {
    "product": "integration_suite",
    "api_url": "https://acme.it-cpi018.cfapps.br10.hana.ondemand.com",
    "token_url": "https://acme.authentication.br10.hana.ondemand.com/oauth/token",
    "page_size": 2,
    "requests_per_minute": 600,
}


def log(n: int, millis: int, status: str = "FAILED") -> dict[str, Any]:
    return {
        "MessageGuid": f"AGVtZXNzYWdl{n:04d}",
        "CorrelationId": f"AGcorrelacao{n:02d}",
        "ApplicationMessageId": f"pedido-{n}",
        "LogStart": f"/Date({millis - 500})/",
        "LogEnd": f"/Date({millis})/",
        "Status": status,
        "CustomStatus": "Timeout no receiver SAP",
        "IntegrationFlowName": "Pedidos_SF_para_SAP",
        "Sender": "Salesforce",
        "Receiver": "S4HANA",
    }


class FakeCpi:
    def __init__(self) -> None:
        # Dois no mesmo milissegundo: desempate pelo Guid.
        self.logs = [log(1, 1731247000000), log(2, 1731247100000), log(3, 1731247100000)]
        self.filters: list[str] = []
        self.tokens = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            self.tokens += 1
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if request.url.path == "/api/v1/MessageProcessingLogs":
            query = request.url.params
            self.filters.append(query["$filter"])
            rows = self.logs
            if "MessageGuid gt '" in query["$filter"]:
                guid = query["$filter"].split("MessageGuid gt '")[1].split("'")[0]
                stamp = query["$filter"].split("LogEnd gt datetime'")[1].split("'")[0]
                cut = datetime.fromisoformat(stamp).replace(tzinfo=UTC)
                rows = [
                    r for r in rows if (odata_date(r["LogEnd"]), r["MessageGuid"]) > (cut, guid)
                ]
            return httpx.Response(200, json={"d": {"results": rows[: int(query["$top"])]}})
        return httpx.Response(404)


def connector(fake: FakeCpi) -> SapIntegrationSuiteConnector:
    async def no_sleep(_: float) -> None:
        return None

    return SapIntegrationSuiteConnector(
        transport=httpx.MockTransport(fake.handler), clock=lambda: NOW, sleep=no_sleep
    )


class TestSapIntegrationSuiteContract(ConnectorContractTests):
    def make_connector(self) -> SapIntegrationSuiteConnector:
        return connector(FakeCpi())

    def valid_config(self) -> Mapping[str, Any]:
        return CONFIG

    def invalid_config(self) -> Mapping[str, Any]:
        return {**CONFIG, "api_url": "https://evil.example.com"}

    def secret(self) -> str:
        return SECRET


def test_mensagens_com_falha_viram_eventos_correlacionaveis_pelo_correlation_id() -> None:
    fake = FakeCpi()

    async def gather() -> list[Any]:
        return [b async for b in connector(fake).collect(Secret(SECRET), CONFIG, None)]

    events = [e for b in asyncio.run(gather()) for e in b.events]
    assert [e["execution_id"] for e in events] == [
        "AGcorrelacao01",
        "AGcorrelacao02",
        "AGcorrelacao03",
    ]
    assert events[0]["severity"] == "ERROR"
    assert events[0]["error"]["message"] == "iFlow Pedidos_SF_para_SAP: Timeout no receiver SAP"
    assert events[0]["source"] == {
        "provider": "sap",
        "service": "integration-suite",
        "resource": "Pedidos_SF_para_SAP",
    }
    assert "Status eq 'FAILED'" in fake.filters[0]
    assert "Status eq 'COMPLETED'" not in fake.filters[0]
    # Segunda página: desempate pelo Guid no mesmo LogEnd.
    assert "MessageGuid gt 'AGVtZXNzYWdl0002'" in fake.filters[1]
    assert fake.tokens == 1


def test_hosts_fora_da_sap_btp_sao_recusados() -> None:
    sap = SapIntegrationSuiteConnector()
    errors = sap.validate_config(
        {
            **CONFIG,
            "api_url": "https://acme.hana.ondemand.com.evil.io",
            "token_url": "https://acme.authentication.br10.hana.ondemand.com/outro",
        }
    )
    assert set(errors) == {"api_url", "token_url"}
    assert sap.validate_config(
        {**CONFIG, "api_url": "http://acme.it-cpi018.cfapps.br10.hana.ondemand.com"}
    )


@pytest.mark.parametrize(
    ("status", "kind"), [(401, "auth"), (403, "auth"), (429, "rate_limit"), (500, "transient")]
)
def test_erros_da_api_classificados(status: int, kind: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(status)

    sap = SapIntegrationSuiteConnector(transport=httpx.MockTransport(handler), clock=lambda: NOW)
    result = asyncio.run(sap.test_connection(Secret(SECRET), CONFIG))
    assert not result.ok
    assert "segredo-da-service-key" not in result.message
    assert kind
