# Alerta: erro do LLM acima de 10%

**Disparo:** na última hora, mais de 10% dos Diagnósticos que chamaram o LLM terminaram em `failed_llm` (`custom.googleapis.com/aid/llm_error_rate_1h`). O Diagnóstico não se perde: ele sai só com as Regras, com o aviso no card.

1. **Provedor fora do ar?** Status do provedor configurado na Organização (`tenants.llm_provider`, padrão Anthropic) e os logs do `worker-diagnosis` com `severity>=WARNING`.
2. **Chave ou cota do provedor:** 401/403/429 nos logs. Rotacione o segredo `anthropic-api-key` no Secret Manager (`docs/operations/ia.md`) ou aguarde o limite do provedor.
3. **Resposta fora do schema** (`schema` duas vezes): um modelo novo ou um prompt alterado. Rode a avaliação (`make eval-hybrid`) e compare com a linha de base (`docs/operations/avaliacao.md`).
4. Enquanto durar, os Diagnósticos novos podem ser pedidos em "Só Regras". O consumo de tokens está em `llm_tokens_1h` no dashboard.
