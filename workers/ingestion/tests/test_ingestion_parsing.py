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


def test_celula_enorme_no_csv_vira_rejeicao_da_linha() -> None:
    data = b"timestamp;mensagem\n2026-11-02T14:05:00Z;ok\n2026-11-02T14:05:01Z;" + b"x" * 200_000
    data += b"\n2026-11-02T14:05:02Z;fim\n"
    result = list(read_records(data, "csv"))
    assert [line.record is not None for line in result] == [True, True, True]


def test_codificacao_decidida_por_linha() -> None:
    data = '{"m": "ação"}\n'.encode() + '{"m": "não"}\n'.encode("latin-1")
    result = list(read_records(data, "ndjson"))
    assert [line.record for line in result] == [{"m": "ação"}, {"m": "não"}]


def test_csv_com_aspas_e_quebra_de_linha_no_campo() -> None:
    data = b'timestamp,mensagem\n2026-11-02T14:05:00Z,"linha 1\nlinha 2"\n'
    result = list(read_records(data, "csv"))
    assert result[0].record == {"timestamp": "2026-11-02T14:05:00Z", "mensagem": "linha 1\nlinha 2"}
