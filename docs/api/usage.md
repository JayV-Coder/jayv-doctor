# Uso e Cotas

`GET /api/v1/usage` (todo Papel): plano, consumo e limite de cada recurso da Organização ativa, e os tokens e o custo estimado de IA do mês.

| Recurso | Período | Piloto | Profissional | Enterprise | Ao chegar no limite |
|---|---|---|---|---|---|
| `events_ingested` | mês | 3 mi | 30 mi | 300 mi | lote acima de 110% (tolerância por Organização) recusado: `429 quota_exceeded`; a Importação também |
| `diagnoses_llm` | mês | 1.000 | 10.000 | 100.000 | o Diagnóstico pedido como híbrido roda em `rules_only`, com a nota "Cota de IA do mês esgotada" no card |
| `storage_bytes` | absoluto | 50 GB | 500 GB | 5 TB | aviso (medido todo dia pelo job de retenção) |
| `connectors_active` | absoluto | 5 | 20 | 200 | criar Conector: `409 plan_limit` |
| `members` | absoluto | 20 | 100 | 1.000 | convidar (contando os convites pendentes) ou aceitar: `409 plan_limit` |

- **Contagem:** `usage_records` com incremento atômico (`insert … on conflict do update`): um trigger por comando em `doctor.events` conta os Eventos gravados (ingestão, Importação e Conectores; o duplicado descartado não entra), e o worker de diagnóstico registra cada Diagnóstico que chamou o LLM em `usage_llm` (provedor, modelo, tokens e custo estimado). Conectores e membros são contados na hora.
- **Imposição em triggers:** vale para todo caminho de escrita (API, token de ingestão, Conectores), não só para a rota da API.
- **Avisos aos 80% e 100%:** uma vez por recurso, período e patamar (`usage_alerts`); a mensagem `usage.threshold` vai para o worker de diagnóstico, que manda e-mail para Owner e Admin. O push fica para a v0.3.
- **Custo estimado:** pela tabela `AID_LLM_PRICES` do worker de diagnóstico (JSON por modelo, `input_per_mtok`/`output_per_mtok`), copiada da tabela oficial do provedor; sem ela, o custo fica em aberto.
- O plano da Organização (`doctor.tenants.plan`) e a tolerância (`quota_tolerance`) mudam só pela plataforma; a cobrança é a v1.0 (#50).
