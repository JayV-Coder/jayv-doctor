"""Mapa de identificadores (#40): validação e chaves normalizadas por sistema."""

from datetime import timedelta

import pytest
from aid_correlation import IdentifierMap, MappingError, cross_keys, dump_keys, parse_keys

MAP = "00000000-0000-4000-8000-00000000ma01"
KEYS = parse_keys(
    [
        {"system": "salesforce", "field": "execution_id"},
        {
            "system": "gcp",
            "field": "attributes.sf_order",
            "transforms": [{"op": "trim"}, {"op": "strip_prefix", "value": "SF-"}],
        },
        {
            "system": "sap",
            "field": "attributes.bstkd",
            "transforms": [{"op": "strip_leading_zeros"}, {"op": "upper"}],
        },
    ]
)
PEDIDO = IdentifierMap(MAP, KEYS, timedelta(minutes=60))


def event(provider: str, **fields: object) -> dict[str, object]:
    return {"source": {"provider": provider, "service": "x"}, **fields}


def test_o_mesmo_pedido_nos_tres_sistemas_vira_a_mesma_chave() -> None:
    expected = (f"{MAP}:801XX0001",)
    assert cross_keys(event("salesforce", execution_id="801XX0001"), [PEDIDO]) == expected
    assert cross_keys(event("gcp", attributes={"sf_order": " SF-801XX0001 "}), [PEDIDO]) == expected
    assert cross_keys(event("sap", attributes={"bstkd": "0000801xx0001"}), [PEDIDO]) == expected


def test_campo_ausente_outro_sistema_ou_valor_vazio_nao_gera_chave() -> None:
    assert cross_keys(event("sap", attributes={}), [PEDIDO]) == ()
    assert cross_keys(event("aws", execution_id="801XX0001"), [PEDIDO]) == ()
    assert cross_keys(event("sap", attributes={"bstkd": "0000"}), [PEDIDO]) == ()
    assert cross_keys(event("sap", attributes={"bstkd": {"x": 1}}), [PEDIDO]) == ()


def test_ida_e_volta_do_formato_salvo() -> None:
    assert parse_keys(dump_keys(KEYS)) == KEYS


@pytest.mark.parametrize(
    "raw",
    [
        [],
        [{"system": "oracle", "field": "execution_id"}],
        [{"system": "sap", "field": "business_context.entity_reference"}],
        [{"system": "sap", "field": "attributes.a.b.c"}],
        [{"system": "sap", "field": "attributes.x y"}],
        [{"system": "sap", "field": "execution_id", "transforms": [{"op": "regex"}]}],
        [{"system": "sap", "field": "execution_id", "transforms": [{"op": "strip_prefix"}]}],
        "execution_id",
    ],
)
def test_mapa_invalido_e_recusado(raw: object) -> None:
    with pytest.raises(MappingError):
        parse_keys(raw)
