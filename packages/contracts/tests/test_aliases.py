"""Nomes de coluna aceitos para cada campo do Contrato de evento (#11): a API sugere o
mapeamento com eles, e o worker de ingestão reconhece as colunas com os mesmos nomes."""

from aid_contracts.aliases import FIELDS, apply_mapping, suggest


def test_sugere_cada_campo_pela_primeira_coluna_reconhecida_sem_repetir_coluna() -> None:
    columns = ["Data", "MSGTY", "Texto", "BAPI", "DOCNUM", "Cliente", "status"]
    assert suggest(columns) == {
        "timestamp": "Data",
        "severity": "MSGTY",
        "operation": "BAPI",
        "execution_id": "DOCNUM",
        "message": "Texto",
        "http_status": "status",
    }


def test_coluna_desconhecida_fica_sem_sugestao() -> None:
    assert suggest(["Coluna A", "Coluna B"]) == {}


def test_o_mapeamento_poe_a_coluna_no_nome_do_contrato_e_o_resto_fica() -> None:
    record = {"Data/Hora": "2026-11-02 14:05", "Texto da mensagem": "Timeout", "Cliente": "ACME"}
    mapped = apply_mapping(record, {"timestamp": "Data/Hora", "message": "Texto da mensagem"})
    assert mapped == {"timestamp": "2026-11-02 14:05", "message": "Timeout", "Cliente": "ACME"}


def test_o_mapeamento_vale_mais_que_a_coluna_de_mesmo_nome_e_ignora_coluna_ausente() -> None:
    record = {"timestamp": "antiga", "Quando": "2026-11-02T14:05:00Z"}
    assert apply_mapping(record, {"timestamp": "Quando", "message": "Não existe"}) == {
        "timestamp": "2026-11-02T14:05:00Z"
    }
    assert apply_mapping(record, {}) is record


def test_campos_sao_os_do_contrato() -> None:
    assert set(FIELDS) == {
        "timestamp",
        "severity",
        "operation",
        "execution_id",
        "trace_id",
        "message",
        "http_status",
        "error_code",
    }
