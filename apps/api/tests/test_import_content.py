from pathlib import Path

import pytest
from aid_api.imports.content import MISMATCH, check_head

FIXTURES = Path(__file__).parent / "fixtures" / "imports"


def head_of(name: str, limit: int = 65536) -> tuple[bytes, int]:
    data = (FIXTURES / name).read_bytes()
    return data[:limit], len(data)


@pytest.mark.parametrize(
    ("name", "file_format"),
    [
        ("sap-orders-bom.ndjson", "ndjson"),
        ("bapi-errors-latin1.csv", "csv"),
        ("eventos.json", "json"),
    ],
    ids=["ndjson-com-bom", "csv-latin1", "json"],
)
def test_aceita_o_formato_declarado(name: str, file_format: str) -> None:
    head, size = head_of(name)
    assert check_head(file_format, head, size) is None


@pytest.mark.parametrize(
    ("name", "file_format"),
    [
        ("pedidos.json", "json"),
        ("imagem.csv", "csv"),
        ("primeira-linha-invalida.ndjson", "ndjson"),
        ("bapi-errors-latin1.csv", "json"),
        ("eventos.json", "csv"),
    ],
    ids=["xml-renomeado", "png-renomeado", "ndjson-invalido", "csv-como-json", "json-como-csv"],
)
def test_recusa_conteudo_que_nao_bate_com_a_extensao(name: str, file_format: str) -> None:
    head, size = head_of(name)
    assert check_head(file_format, head, size) == MISMATCH


def test_arquivo_vazio() -> None:
    assert check_head("csv", b"", 0) == "Arquivo vazio"


def test_json_grande_cortado_no_meio_ainda_passa() -> None:
    data = b'[{"severity": "error", "message": "' + "ç".encode() * 40000 + b'"}]'
    head = data[:65536]
    assert len(head) < len(data)
    assert check_head("json", head, len(data)) is None


def test_ndjson_com_primeira_linha_maior_que_o_trecho() -> None:
    line = b'{"message": "' + b"a" * 70000 + b'"}\n'
    assert check_head("ndjson", line[:65536], len(line)) is None
