from pathlib import Path

from aid_ingestion.parsing import Line, read_records

FIXTURES = Path(__file__).parent / "fixtures"


def lines(name: str, file_format: str) -> list[Line]:
    return list(read_records((FIXTURES / name).read_bytes(), file_format))


def test_ndjson_com_bom_e_linha_invalida() -> None:
    result = lines("sap-orders-bom.ndjson", "ndjson")
    assert [line.number for line in result] == [1, 2, 3]
    assert result[0].record is not None
    assert result[0].record["operation"] == "BAPI_SALESORDER_CREATEFROMDAT2"
    assert result[2].record is None
    assert result[2].reason == "JSON inválido"


def test_csv_latin1_com_ponto_e_virgula_e_linha_quebrada() -> None:
    result = lines("bapi-errors-latin1.csv", "csv")
    assert result[0].record == {
        "timestamp": "2026-11-02T14:05:00Z",
        "operacao": "BAPI_SALESORDER",
        "severidade": "erro",
        "mensagem": "Pedido não encontrado",
    }
    assert result[0].number == 2
    assert result[1].record is None
    assert result[1].reason == "número de colunas diferente do cabeçalho"


def test_json_com_lista_de_objetos() -> None:
    data = b'[{"timestamp": "2026-11-02T14:05:00Z"}, 3, {"timestamp": "x"}]'
    result = list(read_records(data, "json"))
    assert [(line.number, line.reason) for line in result] == [
        (1, None),
        (2, "item não é um objeto JSON"),
        (3, None),
    ]


def test_json_com_um_objeto_so() -> None:
    result = list(read_records(b'{"timestamp": "2026-11-02T14:05:00Z"}', "json"))
    assert len(result) == 1
    assert result[0].record == {"timestamp": "2026-11-02T14:05:00Z"}


def test_json_invalido_inteiro_vira_uma_rejeicao() -> None:
    result = list(read_records(b'[{"a": 1}', "json"))
    assert [(line.number, line.reason) for line in result] == [(1, "JSON inválido")]


def test_linhas_em_branco_sao_ignoradas() -> None:
    result = list(read_records(b'{"a": 1}\n\n  \n{"b": 2}\n', "ndjson"))
    assert [line.number for line in result] == [1, 4]
