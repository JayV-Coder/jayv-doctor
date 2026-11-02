from aid_security import Rules, Sanitizer

sanitizer = Sanitizer()


def clean(value: object, rules: Rules | None = None) -> tuple[object, dict[str, int]]:
    result, report = (Sanitizer(rules) if rules else sanitizer).sanitize(value)
    return result, dict(report.counts)


def test_bearer_vira_marcador_e_conta_um() -> None:
    line = "GET /orders Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJh"
    result, counts = clean(line)
    assert "[REMOVIDO:bearer]" in str(result)
    assert "eyJ" not in str(result)
    assert counts == {"bearer": 1}


def test_campos_sensiveis_pelo_nome_somem_inteiros() -> None:
    record = {
        "headers": {"Authorization": "Basic dXNlcjpzZW5oYQ==", "Cookie": "sid=abc123"},
        "password": "hunter2",
        "client_secret": "s3cr3t",
        "order_id": "4500012345",
    }
    result, counts = clean(record)
    assert result == {
        "headers": {"Authorization": "[REMOVIDO:authorization]", "Cookie": "[REMOVIDO:cookie]"},
        "password": "[REMOVIDO:password]",
        "client_secret": "[REMOVIDO:password]",
        "order_id": "4500012345",
    }
    assert counts == {"authorization": 1, "cookie": 1, "password": 2}


def test_password_em_texto_livre() -> None:
    result, counts = clean("conectando com user=sap password=Init1234; tentativa 2")
    assert result == "conectando com user=sap password=[REMOVIDO:password]; tentativa 2"
    assert counts == {"password": 1}


def test_cpf_e_cnpj_so_com_digito_verificador_valido() -> None:
    result, counts = clean("cliente 529.982.247-25, filial 11.222.333/0001-81, pedido 52998224726")
    assert result == "cliente [REMOVIDO:cpf], filial [REMOVIDO:cnpj], pedido 52998224726"
    assert counts == {"cpf": 1, "cnpj": 1}


def test_cpf_com_digito_errado_fica() -> None:
    result, counts = clean("documento 529.982.247-24")
    assert result == "documento 529.982.247-24"
    assert counts == {}


def test_cartao_so_com_luhn_valido() -> None:
    result, counts = clean("cartão 4111 1111 1111 1111 e lote 4111 1111 1111 1112")
    assert result == "cartão [REMOVIDO:cartao] e lote 4111 1111 1111 1112"
    assert counts == {"cartao": 1}


def test_numero_de_pedido_nao_vira_telefone() -> None:
    result, counts = clean({"order": "4500012345", "msg": "pedido 4500012345 criado"})
    assert result == {"order": "4500012345", "msg": "pedido 4500012345 criado"}
    assert counts == {}


def test_telefone_e_email() -> None:
    result, counts = clean("contato ana.souza@acme.com.br, (11) 98765-4321 ou +55 21 3456-7890")
    assert result == "contato [REMOVIDO:email], [REMOVIDO:telefone] ou [REMOVIDO:telefone]"
    assert counts == {"email": 1, "telefone": 2}


def test_ips_configuraveis() -> None:
    line = "origem 10.0.0.12 destino 200.155.10.1"
    assert clean(line)[0] == "origem [REMOVIDO:ip] destino [REMOVIDO:ip]"
    assert clean(line, Rules(allow_private_ips=True))[0] == "origem 10.0.0.12 destino [REMOVIDO:ip]"
    assert clean(line, Rules(detect_ips=False))[0] == line


def test_padroes_extras_do_tenant() -> None:
    rules = Rules(extra_patterns={"matricula": r"\bMAT-\d{6}\b"})
    result, counts = clean("funcionário MAT-123456 aprovou", rules)
    assert result == "funcionário [REMOVIDO:matricula] aprovou"
    assert counts == {"matricula": 1}


def test_chaves_de_nuvem() -> None:
    line = (
        "aws AKIAIOSFODNN7EXAMPLE gcp AIzaSyA1234567890abcdefghijklmnopqrstuv "
        "sf 00D5g000000abcd!AQ4AQFjZ0123456789abcdefghijklmn"
    )
    result, counts = clean(line)
    assert (
        result == "aws [REMOVIDO:aws_key] gcp [REMOVIDO:gcp_key] sf [REMOVIDO:salesforce_session]"
    )
    assert counts == {"aws_key": 1, "gcp_key": 1, "salesforce_session": 1}


def test_numeros_que_sao_cpf_tambem_saem() -> None:
    result, counts = clean({"documento": 52998224725, "quantidade": 3})
    assert result == {"documento": "[REMOVIDO:cpf]", "quantidade": 3}
    assert counts == {"cpf": 1}


def test_string_longa_e_truncada_com_marcador() -> None:
    result, report = sanitizer.sanitize("a" * 10_000)
    assert isinstance(result, str)
    assert result.endswith("[TRUNCADO]")
    assert len(result.encode()) <= 8192 + len("[TRUNCADO]")
    assert report.truncated == 1


def test_json_profundo_e_cortado_no_nivel_10() -> None:
    record: object = "fundo"
    for _ in range(15):
        record = {"n": record}
    result, report = sanitizer.sanitize(record)
    depth = 0
    node = result
    while isinstance(node, dict):
        node = node["n"]
        depth += 1
    assert depth == 10
    assert node == "[TRUNCADO:profundidade]"
    assert report.truncated == 1
