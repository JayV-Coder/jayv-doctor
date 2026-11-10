"""Conector OData só de consulta (ticket #40), contra um serviço falso em memória."""

import asyncio
import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest
from aid_connectors.base import ConnectorError, LookupQuery, Secret
from aid_connectors.odata.connector import ODataConnector, PublicOnlyBackend, shape_ok

URL = "https://s4.acme.com.br/sap/opu/odata/sap/API_SALES_ORDER_SRV"
CONFIG: dict[str, Any] = {"service_url": URL, "version": "v2", "auth": "basic"}
SECRET = Secret(json.dumps({"username": "AID_READER", "password": "segredo-de-teste"}))
QUERY = LookupQuery(
    "A_SalesOrder", "PurchaseOrderByCustomer", "801XX0001", "OverallSDProcessStatus", "SalesOrder"
)


class FakeOData:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path.endswith("/$metadata"):
            return httpx.Response(200, text="<edmx:Edmx/>")
        query = parse_qs(urlparse(str(request.url)).query)
        wanted = unquote(query["$filter"][0])
        rows = []
        if wanted == "PurchaseOrderByCustomer eq '801XX0001'":
            rows = [
                {
                    "PurchaseOrderByCustomer": "801XX0001",
                    "SalesOrder": "12345",
                    "OverallSDProcessStatus": "C",
                }
            ]
        return httpx.Response(200, json={"d": {"results": rows}})


def public(*addresses: str) -> Any:
    async def resolver(_: str) -> Sequence[str]:
        return addresses

    return resolver


def run(connector: ODataConnector, query: LookupQuery, config: Mapping[str, Any] = CONFIG) -> Any:
    return asyncio.run(connector.lookup(SECRET, config, query))


def test_consulta_acha_o_pedido_e_traz_o_status() -> None:
    fake = FakeOData()
    connector = ODataConnector(httpx.MockTransport(fake.handler), public("200.160.2.3"))
    found = run(connector, QUERY)
    assert (found.found, found.record_id, found.status) == (True, "12345", "C")
    request = fake.requests[-1]
    assert request.headers["authorization"].startswith("Basic ")
    assert request.url.path.endswith("/A_SalesOrder")
    assert "%24top=1" in str(request.url) or "$top=1" in str(request.url)
    assert (
        run(connector, LookupQuery("A_SalesOrder", "PurchaseOrderByCustomer", "999")).found is False
    )


def test_aspas_dobradas_no_filtro_e_nomes_fora_do_padrao_recusados() -> None:
    fake = FakeOData()
    connector = ODataConnector(httpx.MockTransport(fake.handler), public("200.160.2.3"))
    run(connector, LookupQuery("A_SalesOrder", "PurchaseOrderByCustomer", "x' or 1 eq 1 or 'a"))
    wanted = unquote(parse_qs(urlparse(str(fake.requests[-1].url)).query)["$filter"][0])
    assert wanted == "PurchaseOrderByCustomer eq 'x'' or 1 eq 1 or ''a'"
    with pytest.raises(ConnectorError):
        run(connector, LookupQuery("A_SalesOrder?$expand=to_Item", "X", "1"))


@pytest.mark.parametrize(
    "addresses",
    [("10.0.0.5",), ("127.0.0.1",), ("169.254.169.254",), ("200.160.2.3", "192.168.0.10")],
)
def test_host_que_resolve_para_rede_interna_e_recusado(addresses: tuple[str, ...]) -> None:
    fake = FakeOData()
    connector = ODataConnector(httpx.MockTransport(fake.handler), public(*addresses))
    with pytest.raises(ConnectorError) as raised:
        run(connector, QUERY)
    assert raised.value.kind == "invalid"
    assert fake.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "http://s4.acme.com.br/sap/opu/odata/sap/X",
        "https://10.0.0.5/sap/opu/odata/sap/X",
        "https://user:pw@s4.acme.com.br/sap/X",
        "https://s4.acme.com.br:8443/sap/X",
        "https://s4.acme.com.br/sap/X?sap-client=100",
        "http://127.0.0.1:1@evil.com/x",
    ],
)
def test_endereco_fora_da_regra_nem_chega_a_resolver(url: str) -> None:
    assert not shape_ok(url)
    assert ODataConnector().validate_config({**CONFIG, "service_url": url}) != {}


def test_v4_sem_format_e_teste_de_conexao_pelo_metadata() -> None:
    fake = FakeOData()
    connector = ODataConnector(httpx.MockTransport(fake.handler), public("200.160.2.3"))
    result = asyncio.run(connector.test_connection(SECRET, {**CONFIG, "version": "v4"}))
    assert result.ok
    assert fake.requests[-1].url.path.endswith("/$metadata")
    run(connector, QUERY, {**CONFIG, "version": "v4"})
    assert "format" not in str(fake.requests[-1].url)


def test_credencial_sem_campos_e_erro_de_autenticacao() -> None:
    connector = ODataConnector(httpx.MockTransport(FakeOData().handler), public("200.160.2.3"))
    with pytest.raises(ConnectorError) as raised:
        asyncio.run(connector.lookup(Secret("{}"), CONFIG, QUERY))
    assert raised.value.kind == "auth"


def test_nao_coleta_eventos() -> None:
    async def gather() -> list[Any]:
        return [b async for b in ODataConnector().collect(SECRET, CONFIG, None)]

    assert asyncio.run(gather()) == []


@pytest.mark.parametrize("address", ["10.0.0.5", "127.0.0.1", "169.254.169.254"])
def test_a_conexao_so_vai_para_o_endereco_conferido(address: str) -> None:
    """DNS rebinding: a rede do transporte resolve e confere na hora de conectar."""
    import httpcore

    backend = PublicOnlyBackend(public(address))
    with pytest.raises(httpcore.ConnectError):
        asyncio.run(backend.connect_tcp("s4.acme.com.br", 443))
