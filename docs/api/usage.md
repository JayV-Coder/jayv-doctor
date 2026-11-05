# Uso e Cotas

`GET /api/v1/usage` (todo Papel): plano, tolerância da Cota de Eventos, consumo e limite de cada recurso da Organização ativa, e os tokens e o custo estimado de IA do mês (mês em UTC).

| Recurso | Período | Piloto | Profissional | Enterprise | Ao chegar no limite |
|---|---|---|---|---|---|
| `events_ingested` | mês | 3 mi | 30 mi | 300 mi | lote acima de 110% (tolerância por Organização) recusado: `429 quota_exceeded`; a Importação também |
| `diagnoses_llm` | mês | 1.000 | 10.000 | 100.000 | o Diagnóstico pedido como híbrido roda em `rules_only`, com a nota "Cota de IA do mês esgotada" no card |
| `storage_bytes` | absoluto | 50 GB | 500 GB | 5 TB | aviso (medido todo dia pelo job de retenção) |
| `connectors_active` | absoluto | 5 | 20 | 200 | criar Conector: `409 plan_limit` |
| `members` | absoluto | 20 | 100 | 1.000 | convidar (contando os convites pendentes, que a tela também mostra): `409 plan_limit` |

- **Eventos:** um trigger por comando em `doctor.events` grava os Eventos de fato inseridos (ingestão, Importação e Conectores; o duplicado descartado não entra) como deltas em `usage_deltas`, só com insert, para as transações de ingestão não disputarem a mesma linha. O job de 10 min do worker de correlação (`rollup_usage`) os soma em `usage_records`; a leitura e a imposição já contam os deltas pendentes.
- **IA:** antes de chamar o LLM, o worker reserva uma unidade com `reserve_llm_quota` (incremento condicional, atômico: Diagnósticos em paralelo não passam do limite; a mesma entrega não reserva duas vezes). Os tokens e o custo estimado entram em `usage_llm` na mesma transação da publicação do Diagnóstico. Conectores e membros são contados na hora.
- **Imposição em triggers:** vale para todo caminho de escrita (API, token de ingestão, Conectores), não só para a rota da API.
- **Avisos aos 80% e 100%:** uma vez por recurso, período e patamar (`usage_alerts`), também para o armazenamento medido no job diário; a mensagem `usage.threshold` vai para o worker de diagnóstico, que manda e-mail para Owner e Admin. O push fica para a v0.3.
- **Conector com a Cota de Eventos esgotada:** a Sincronização termina com a mensagem da Cota, sem contar falha nem entrar em `failing`; o Conector tenta de novo de hora em hora.
- **Custo estimado:** pela tabela `AID_LLM_PRICES` do worker de diagnóstico (JSON por modelo, `input_per_mtok`/`output_per_mtok`), copiada da tabela oficial do provedor e lida uma vez na subida; entrada inválida é ignorada com aviso no log, e o custo daquele modelo fica em aberto.
- O plano da Organização (`doctor.tenants.plan`) e a tolerância (`quota_tolerance`) mudam só pela plataforma; a cobrança é a v1.0 (#50).
