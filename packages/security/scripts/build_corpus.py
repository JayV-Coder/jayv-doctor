"""Gera tests/corpus/corpus.jsonl: casos positivos e negativos para medir o Sanitizer.

Os valores válidos são exemplos públicos conhecidos (CPF/CNPJ de documentação, cartões de teste
das bandeiras), e não saem do código testado. Rode `uv run python packages/security/scripts/
build_corpus.py` depois de mudar as listas; o arquivo gerado é versionado para revisão.
"""

import json
from pathlib import Path

TEMPLATES = [
    "ERROR BAPI_SALESORDER_CREATEFROMDAT2 retorno E: {v} rejeitado",
    '[sf-sync] payload {{"campo": "{v}", "status": "erro"}}',
    "{v}",
]

POSITIVES: dict[str, list[str]] = {
    "cpf": ["529.982.247-25", "111.444.777-35", "123.456.789-09", "52998224725", "11144477735"],
    "cnpj": ["11.222.333/0001-81", "11.444.777/0001-61", "11222333000181", "11444777000161"],
    "cartao": [
        "4111 1111 1111 1111",
        "5555-5555-5555-4444",
        "378282246310005",
        "4012888888881881",
        "6011111111111117",
    ],
    "email": ["ana.souza@acme.com.br", "integracao+sap@varejo.com", "ops@industria.ind.br"],
    "telefone": [
        "(11) 98765-4321",
        "+55 21 3456-7890",
        "11 98765-4321",
        "(21) 3456-7890",
        "+5511987654321",
    ],
    "ip": ["200.155.10.1", "8.8.8.8", "10.0.0.12", "192.168.0.10"],
    "bearer": [
        "Bearer 9f8e7d6c5b4a39281706f5e4d3c2b1a0",
        "bearer AbCdEfGhIjKlMnOpQrStUvWx.yz-123",
    ],
    "jwt": [
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.dGVzdGVzaWduYXR1cmE",
        "eyJ0eXAiOiJKV1QifQ.eyJhdWQiOiJzYXAifQ.c2ln",
    ],
    "aws_key": ["AKIAIOSFODNN7EXAMPLE", "ASIAY34FZKBOKMUTVV7A"],
    "gcp_key": ["AIzaSyD-9tSrke72PouQMnMX-a7eZSW0jkFMBWY"],
    "gcp_token": ["ya29.a0AfH6SMBx3jFz1Lq8kR2pT9vW4yN6mC0dE"],
    "salesforce_session": ["00D5g000000abcd!AQ4AQFjZ0123456789abcdefghijklmn"],
    "password": [
        "password=Init1234",
        "senha: Sap@2026",
        "pwd='segredo-forte'",
        '"password": "hunter22"',
        "DB_PASSWORD=hunter2xyz",
        "x-api-key: abcdef123456",
    ],
    "token": ["access_token=opaqueABC123xyz", "refresh_token: 1//0gAbCdEf"],
    "authorization": ["Authorization: Basic dXNlcjpzZW5oYQ=="],
    "cookie": ["Cookie: sid=31d4d96e407aad42; lang=pt-BR"],
    "private_key": [
        "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\\n-----END PRIVATE KEY-----"
    ],
}

NEGATIVES = [
    "pedido 4500012345 criado",
    "documento SAP 0080001234 lançado",
    "IDoc 0000000001234567 status 51",
    "CPF 529.982.247-24 inválido no cadastro",
    "CNPJ 11.222.333/0001-80 recusado",
    "cartão 4111 1111 1111 1112 recusado pela adquirente",
    "timestamp 2026-11-02T14:05:00.123Z",
    "data 02/11/2026 14:05",
    "trace 4bf92f3577b34da6a3ce929d0e0e4736",
    "id 3f2504e0-4f89-41d3-9a0c-0305e82c3301",
    "sha256 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "HTTP 504 Gateway Timeout após 30000 ms",
    "valor R$ 1.234,56 em 3 parcelas",
    "Bearer token missing",
    "password expired for user SAPUSER",
    "token expirado, renovando sessão",
    "cookie de sessão ausente",
    "authorization failed: escopo insuficiente",
    "BAPI_SALESORDER_CREATEFROMDAT2 retornou TYPE=E NUMBER=219",
    "material 000000000000100234 sem estoque",
    "quantidade 12 unidade PC centro 1000",
    "lote 2026110201 expedido",
    "versão do conector 1.4.2",
    "porta 8443 recusou conexão",
    "Opportunity 0065g00000AbCdE atualizada",
    "Account 0015g00000XyZ12 sincronizada",
    "chave de partição 202611",
    "fila sap-orders com 1532 mensagens",
    "retry 3/5 em 2000 ms",
    "user agent Mozilla/5.0 (X11; Linux x86_64)",
    "SKU 7891234567895 sem preço",
    "nota fiscal 000123456 série 1",
    "duração 00:01:23.456",
    "processo 12345 PID 6789",
    "CEP 01310-100 inválido",
    "status code 422 Unprocessable Entity",
    "endpoint /api/v1/orders/4500012345",
    "região southamerica-east1",
    "AIza curto não é chave",
    "AKIA sozinho não é chave",
    "tokenType=Bearer",
    "password_expires_at=2026-12-01",
]


def main() -> None:
    cases = []
    for kind, values in POSITIVES.items():
        for value in values:
            for template in TEMPLATES:
                text = template.format(v=value)
                cases.append({"id": f"{kind}-{len(cases)}", "text": text, "expect": {kind: 1}})
    for value in NEGATIVES:
        for template in TEMPLATES:
            cases.append(
                {"id": f"neg-{len(cases)}", "text": template.format(v=value), "expect": {}}
            )
    target = Path(__file__).parents[1] / "tests" / "corpus" / "corpus.jsonl"
    target.write_text("".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cases))
    print(f"{len(cases)} casos em {target}")


if __name__ == "__main__":
    main()
