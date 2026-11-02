# aid-security

Sanitização de segredos e dados pessoais e HMAC de Referências de negócio (ticket #13, PRD §8). Roda antes da persistência analítica e de qualquer envio ao LLM.

```python
from aid_security import Rules, Sanitizer, derive_tenant_key

key = derive_tenant_key(master_key, tenant_id)  # HKDF-SHA256 da chave mestre (Secret Manager)
sanitizer = Sanitizer(
    rules=Rules(extra_patterns={"matricula": r"\bMAT-\d{6}\b"}, allow_private_ips=True),
    reference_fields=("order_id", "customer_document"),  # configuração da Integração
    reference_key=key,
)
record, report = sanitizer.sanitize(raw)  # report.as_dict() vai para sanitization_report
```

## O que sai

| Tipo | Como é achado |
|---|---|
| `bearer`, `jwt`, `aws_key`, `gcp_key`, `gcp_token`, `salesforce_session`, `private_key` | Padrão do provedor; Bearer só com 16+ caracteres |
| `password` | `password=`, `senha:`, `"client_secret": "…"` e parecidos (só o valor) |
| `authorization`, `cookie` | Cabeçalho em texto, ou campo com esse nome |
| `cartao` | 13 a 19 dígitos com Luhn válido |
| `cpf`, `cnpj` | Com dígito verificador válido: número parecido fica |
| `email`, `telefone` | Telefone só com formato (`+55`, DDD entre parênteses ou separador): pedido de 10 dígitos fica |
| `ip` | IPv4; `Rules(detect_ips=False)` desliga, `allow_private_ips=True` mantém os internos |

- Campos com nome sensível (`password`, `token`, `authorization`, `cookie`, `api_key` e outros) somem inteiros, em qualquer nível.
- Números também são conferidos: um CPF guardado como inteiro vira marcador.
- Todos os detectores olham o texto original. Em trechos sobrepostos vale o primeiro da ordem: segredos antes de PII, e cartão e CNPJ antes de CPF e telefone.
- Limites: 8 KB por string (o resto é cortado, com `[TRUNCADO]`) e profundidade 10 (`[TRUNCADO:profundidade]`).

## Referência de negócio

`reference_hmac(key, "4500012345")` → `hmac:<16 hex>`. A chave é derivada por tenant, então o mesmo pedido gera valores diferentes em cada Organização e iguais dentro dela. A busca exata aplica o mesmo HMAC ao termo digitado.

## Medição

- `tests/test_corpus.py`: o corpus `tests/corpus/corpus.jsonl` (246 casos, gerados por `scripts/build_corpus.py` a partir de listas com valores públicos de exemplo) passa nas três metas:
  - precisão de 100% e recall de 100% nos segredos;
  - recall ≥ 99% em PII;
  - negativos intactos.
- `tests/test_fuzz.py` (Hypothesis): nunca lança exceção, e a saída só cresce o tamanho dos marcadores.
- `uv run python packages/security/scripts/benchmark.py` mede um registro típico. Nesta máquina deu cerca de 14 mil registros/s por núcleo; a meta é 10 mil.
