import httpx
from aid_knowledge.storage import missing


def response(status: int, body: object) -> httpx.Response:
    return httpx.Response(status, json=body)


def test_so_o_404_do_storage_e_arquivo_ausente() -> None:
    assert missing(response(404, {}))
    assert missing(response(400, {"statusCode": "404", "error": "not_found"}))
    # Chave de serviço inválida ou bucket errado: configuração, não arquivo sumido.
    assert not missing(response(400, {"statusCode": "403", "error": "Invalid JWT"}))
    assert not missing(response(400, {"statusCode": "404", "error": "Bucket not found"}))
    assert not missing(httpx.Response(400, text="erro"))
