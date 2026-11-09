"""Conector Salesforce (ticket #37) contra um Salesforce falso em memória."""

import asyncio
import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import jwt
import pytest
from aid_connectors.base import ConnectorError, Secret
from aid_connectors.salesforce.auth import trusted_instance
from aid_connectors.salesforce.connector import SalesforceConnector
from aid_connectors.salesforce.soql import (
    APEX_LOG,
    Filter,
    QueryNotAllowedError,
    integration_log,
    select,
)
from aid_connectors.testing import ConnectorContractTests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = KEY.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
).decode()
SECRET = json.dumps(
    {"client_id": "3MVG9-conectado", "username": "doctor@acme.test", "private_key": PEM}
)
CONFIG: dict[str, Any] = {
    "environment": "production",
    "auth": "jwt_bearer",
    "sources": ["integration_log", "apex_log", "event_log_file"],
    "integration_log": {
        "object": "Integration_Log__c",
        "timestamp_field": "CreatedDate",
        "operation_field": "Operation__c",
        "severity_field": "Level__c",
        "message_field": "Message__c",
        "status_code_field": "Status_Code__c",
        "execution_field": "Correlation_Id__c",
        "filters": [{"field": "Level__c", "operator": "!=", "value": "DEBUG"}],
    },
    "page_size": 2,
    "requests_per_minute": 600,
}


def log(n: int, second: int) -> dict[str, Any]:
    return {
        "Id": f"a0B5f000000{n:04d}AAA",
        "SystemModstamp": f"2026-11-10T14:00:{second:02d}.000+0000",
        "CreatedDate": f"2026-11-10T14:00:{second:02d}.000+0000",
        "Operation__c": "CreateOrder",
        "Level__c": "ERROR" if n % 2 else "INFO",
        "Message__c": "Read timed out" if n % 2 else None,
        "Status_Code__c": 504 if n % 2 else 200,
        "Correlation_Id__c": f"pedido-{n}",
    }


class FakeSalesforce:
    """Token, describeGlobal e query, com o `Sforce-Limit-Info` de cada resposta."""

    def __init__(
        self,
        objects: tuple[str, ...] = ("Integration_Log__c", "ApexLog", "EventLogFile"),
        used: int = 100,
    ) -> None:
        self.objects = objects
        self.used = used
        self.queries: list[str] = []
        self.tokens: list[Mapping[str, list[str]]] = []
        # Três registros, dois no mesmo segundo (desempate pelo Id).
        self.records = [log(1, 1), log(2, 2), log(3, 2)]

    def handler(self, request: httpx.Request) -> httpx.Response:
        headers = {"sforce-limit-info": f"api-usage={self.used}/15000"}
        if request.url.path == "/services/oauth2/token":
            self.tokens.append(parse_qs(request.content.decode()))
            return httpx.Response(
                200,
                json={
                    "access_token": "00D-sessao",
                    "instance_url": "https://acme.my.salesforce.com",
                },
            )
        if request.url.path.endswith("/sobjects"):
            return httpx.Response(
                200, json={"sobjects": [{"name": n} for n in self.objects]}, headers=headers
            )
        if request.url.path.endswith("/query"):
            query = unquote(parse_qs(urlparse(str(request.url)).query)["q"][0])
            self.queries.append(query)
            if "FROM Integration_Log__c" in query:
                rows = self.records
                if "Id > '" in query:
                    after = query.split("Id > '")[1].split("'")[0]
                    stamp = query.split("SystemModstamp > ")[1].split(" ")[0]
                    rows = [
                        r for r in rows if (r["SystemModstamp"][:19], r["Id"]) > (stamp[:19], after)
                    ]
                limit = int(query.rsplit("LIMIT ", 1)[1])
                return httpx.Response(200, json={"records": rows[:limit]}, headers=headers)
            if "FROM ApexLog" in query and "Id > '" not in query:
                record = {
                    "Id": "07L5f00000ApexAAA",
                    "SystemModstamp": "2026-11-10T14:01:00.000+0000",
                    "StartTime": "2026-11-10T14:01:00.000+0000",
                    "Operation": "/services/apexrest/orders",
                    "Status": "System.CalloutException: Read timed out",
                    "Request": "API",
                    "DurationMilliseconds": 30000,
                    "LogLength": 1024,
                }
                return httpx.Response(200, json={"records": [record]}, headers=headers)
            return httpx.Response(200, json={"records": []}, headers=headers)
        return httpx.Response(404)


def connector(fake: FakeSalesforce) -> SalesforceConnector:
    async def no_sleep(_: float) -> None:
        return None

    return SalesforceConnector(transport=httpx.MockTransport(fake.handler), sleep=no_sleep)


class TestSalesforceContract(ConnectorContractTests):
    def make_connector(self) -> SalesforceConnector:
        return connector(FakeSalesforce())

    def valid_config(self) -> Mapping[str, Any]:
        return CONFIG

    def invalid_config(self) -> Mapping[str, Any]:
        return {**CONFIG, "sources": ["Account"]}

    def secret(self) -> str:
        return SECRET


def collect(fake: FakeSalesforce, checkpoint: Any = None) -> list[Any]:
    async def gather() -> list[Any]:
        return [b async for b in connector(fake).collect(Secret(SECRET), CONFIG, checkpoint)]

    return asyncio.run(gather())


def test_jwt_bearer_assinado_para_o_host_de_login_sem_senha() -> None:
    fake = FakeSalesforce()
    collect(fake)
    grant = fake.tokens[0]
    assert grant["grant_type"] == ["urn:ietf:params:oauth:grant-type:jwt-bearer"]
    claims = jwt.decode(
        grant["assertion"][0],
        KEY.public_key(),
        algorithms=["RS256"],
        audience="https://login.salesforce.com",
    )
    assert (claims["iss"], claims["sub"]) == ("3MVG9-conectado", "doctor@acme.test")
    assert "password" not in grant


def test_desempate_pelo_id_no_mesmo_systemmodstamp_sem_perder_nem_repetir() -> None:
    fake = FakeSalesforce()
    batches = collect(fake)
    logs = [e for b in batches for e in b.events if e["source"]["service"] == "Integration_Log__c"]
    assert [e["attributes"]["salesforce_id"] for e in logs] == [r["Id"] for r in fake.records]
    second = next(q for q in fake.queries if "FROM Integration_Log__c" in q and "Id > '" in q)
    assert "OR (SystemModstamp = 2026-11-10T14:00:02.000Z AND Id > 'a0B5f0000000002AAA')" in second
    assert "Level__c != 'DEBUG'" in second
    error = next(e for e in logs if e["severity"] == "ERROR")
    assert error["error"] == {
        "category": "TIMEOUT",
        "http_status": 504,
        "message": "Read timed out",
    }
    assert error["execution_id"] == "pedido-1"


def test_org_sem_event_monitoring_informa_e_segue_com_as_outras_fontes() -> None:
    fake = FakeSalesforce(objects=("Integration_Log__c", "ApexLog"))
    result = asyncio.run(connector(fake).test_connection(Secret(SECRET), CONFIG))
    assert result.ok
    assert "EventLogFile indisponível nesta edição" in result.message
    assert result.capabilities == {
        "integration_log": True,
        "apex_log": True,
        "event_log_file": False,
    }
    batches = collect(fake)
    assert batches
    assert not any("EventLogFile" in q for q in fake.queries)


def test_80_por_cento_do_limite_diario_pausa_ate_a_janela_seguinte() -> None:
    fake = FakeSalesforce(used=12_000)
    with pytest.raises(ConnectorError) as raised:
        collect(fake)
    assert raised.value.kind == "api_limit"
    assert raised.value.retry_after == 3600
    assert "80%" in raised.value.message
    assert fake.queries == []


def test_nenhuma_consulta_fora_da_allowlist() -> None:
    allowlist = {APEX_LOG.object: APEX_LOG}
    log_source = integration_log("Integration_Log__c", ["Message__c"], "Message__c")
    with pytest.raises(QueryNotAllowedError, match="allowlist"):
        select(log_source, allowlist, after=None, limit=10)
    with pytest.raises(QueryNotAllowedError, match="LIMIT"):
        select(APEX_LOG, allowlist, after=None, limit=0)
    with pytest.raises(QueryNotAllowedError, match="LIMIT"):
        select(APEX_LOG, allowlist, after=None, limit=50_000)
    with pytest.raises(QueryNotAllowedError, match="filtro"):
        select(APEX_LOG, allowlist, after=None, limit=10, filters=[Filter("Password", "=", "x")])
    with pytest.raises(QueryNotAllowedError, match="filtro"):
        select(APEX_LOG, allowlist, after=None, limit=10, filters=[Filter("Status", "LIKE", "%")])
    with pytest.raises(QueryNotAllowedError, match="objeto customizado"):
        integration_log("Account", ["Name"], "Name")
    with pytest.raises(QueryNotAllowedError, match="campos"):
        integration_log("Log__c", ["Name FROM User --"], "Name FROM User --")
    # Valor de filtro com aspas fica dentro da string.
    query = select(
        APEX_LOG, allowlist, after=None, limit=10, filters=[Filter("Status", "=", "x' OR Id != '")]
    )
    assert "Status = 'x\\' OR Id != \\''" in query
    with pytest.raises(QueryNotAllowedError, match="valor"):
        select(APEX_LOG, allowlist, after=None, limit=10, filters=[Filter("Status", "=", "a\nb")])


def test_config_com_soql_livre_ou_objeto_padrao_e_recusada() -> None:
    sf = SalesforceConnector()
    assert "sources" in sf.validate_config({**CONFIG, "sources": ["select Id from User"]})
    bad = {**CONFIG, "integration_log": {**CONFIG["integration_log"], "object": "User"}}
    assert "integration_log" in sf.validate_config(bad)
    outside = {
        **CONFIG,
        "integration_log": {
            **CONFIG["integration_log"],
            "filters": [{"field": "OwnerId", "value": "1"}],
        },
    }
    assert "integration_log" in sf.validate_config(outside)


def test_instancia_fora_do_salesforce_e_recusada() -> None:
    assert (
        trusted_instance("https://acme.my.salesforce.com", "https://login.salesforce.com")
        == "https://acme.my.salesforce.com"
    )
    for url in (
        "https://acme.evil.com",
        "http://acme.my.salesforce.com",
        "https://acme.my.salesforce.com.evil.io",
        "http://127.0.0.1:8096",
    ):
        with pytest.raises(ConnectorError):
            trusted_instance(url, "https://login.salesforce.com")


def test_web_server_flow_usa_o_refresh_token() -> None:
    fake = FakeSalesforce()
    secret = json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "r"})
    config = {**CONFIG, "auth": "web_server", "sources": ["apex_log"]}

    async def run() -> None:
        async for _ in connector(fake).collect(Secret(secret), config, None):
            pass

    asyncio.run(run())
    assert fake.tokens[0]["grant_type"] == ["refresh_token"]
    assert fake.tokens[0]["refresh_token"] == ["r"]
