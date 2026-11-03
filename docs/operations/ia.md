# Acesso ao LLM

O motor de diagnóstico chega ao LLM só por `GuardedLLM` (`packages/diagnosis-engine/src/aid_diagnosis_engine/llm`), sobre o provedor da Organização (`tenants.llm_provider`, ADR-0007). Trocar o provedor de uma Organização é um `update` na coluna, sem deploy.

| Provedor | Modelos | Embeddings | Credencial |
|---|---|---|---|
| `anthropic` (padrão) | `claude-sonnet-5-5` (tier `reasoning`), `claude-haiku-5-5` (`fast`) | Voyage `voyage-3`, 1024 dimensões | `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY` (Secret Manager) |
| `vertex` | Gemini `gemini-2.5-pro` / `gemini-2.5-flash` em southamerica-east1 | `text-embedding-005`, 768 dimensões | conta de serviço do Cloud Run, `GCP_PROJECT_ID` |

A dimensão do embedding é do provedor: trocar de provedor numa Organização com Base de conhecimento exige reindexar (#26).

## Guardas (PRD §8)

- **Dados não confiáveis:** cada log e documento vai entre `<untrusted_data id="NONCE" kind=… ref=…>` e `</untrusted_data id="NONCE">`, com um nonce novo por chamada. O sistema diz, antes de tudo, que o conteúdo é dado e nunca instrução. Um delimitador escrito pelo cliente perde os sinais de tag (`‹`, `›`) e não abre nem fecha nada.
- **Sem ferramentas:** nenhuma ferramenta é declarada. A resposta estruturada vem de *structured outputs* (`messages.parse` com o schema Pydantic), não de *tool use*: o Sonnet 5.5 e o Haiku 5.5 recusam `tool_choice` forçado (400), e o formato de saída já garante o schema. É o desvio em relação ao texto do ticket #22.
- **Validação:** Pydantic no schema e, opcionalmente, uma checagem do chamador (toda Evidência citada existe). Saída recusada ganha 1 nova tentativa com o erro; na segunda, `LLMInvalidOutputError` e o diagnóstico fica `failed_llm`, com o resultado das Regras disponível.
- **Orçamento de entrada:** 60 mil tokens por chamada; as Evidências entram em ordem de relevância enquanto couberem, inteiras.
- **Resiliência:** timeout de 90 s, até 3 tentativas com backoff e jitter em 429/5xx/rede, e circuit breaker por provedor no processo (5 falhas abrem por 60 s; na meia-abertura passa uma chamada só). Credencial ausente, 413, 422 e afins não são repetidos. Os retries do SDK ficam desligados para não somar.
- **Recusa do modelo:** vira `LLMUnavailableError` (modo degradado). Não há fallback automático para outro modelo.
- **Cache:** por hash de (Organização, provedor, tier, sistema, instruções, cada Evidência, schema), por 24 h. O nonce não entra na chave. A checagem do chamador roda também na resposta guardada (Evidência apagada invalida o acerto). Hoje em memória, por processo, com teto de entradas.
- **Uso:** cada chamada gera um `Usage` (provedor, modelo, tokens, latência) para `usage_records` (#31), sem conteúdo, inclusive quando falha depois de cobrada (recusa, resposta cortada, fora do schema) e no acerto de cache (tokens zero).
- **Gemini:** o tier `reasoning` tem orçamento de pensamento de 2.048 tokens, somado ao teto pedido, e os tokens de pensamento entram no uso. Bloqueio de segurança (`SAFETY` e afins) é recusa, como no Claude.

## Red team

`packages/diagnosis-engine/tests/test_llm.py` tem 30 tentativas de injeção em logs. No CI, com o `FakeProvider`, elas verificam a estrutura: o conteúdo fica num único par de delimitadores, e um "modelo" que obedece à injeção, citando Evidência inexistente, é barrado na validação. A rodada semanal contra o provedor real entra com o Diagnóstico (#24), quando houver a chave no ambiente.
