# Capacidade e dimensionamento

Premissa do PRD §12: **100 mil Eventos por dia** e **1.000 Diagnósticos por mês** no piloto. Os testes de carga (`tests/load`, ticket #33) exercitam 3× essa premissa e um pico.

> **Estado:** os scripts e o relatório estão prontos e foram validados contra a stack local. As rodadas em staging e os números medidos entram na tabela de [Resultados](#resultados) quando o ambiente estiver configurado (pendência em [pendencias.md](pendencias.md)). Até lá, os valores abaixo são o dimensionamento inicial calculado, não medido.

## Metas

| Cenário | Carga | Meta |
|---|---|---|
| Ingestão sustentada | 3,5 Eventos/s (3× a premissa), 30 min | lag p95 < 60 s, zero perda |
| Pico de ingestão | 200 Eventos/s por 10 min (lotes de 200) | zero perda, sem 5xx acima de 0,1% |
| API de leitura | 50 Usuários simultâneos (Dashboard, Incidentes, Execuções) | p95 < 500 ms, sem 5xx acima de 0,1% |
| Diagnósticos | 100 em 1 h | todos terminados; tempo até a publicação registrado |

- **Lag de ingestão:** `events.ingested_at − events.timestamp`. O k6 envia o Evento com o instante do envio, então o lag soma API, outbox, relay (1 min), Pub/Sub e o worker de ingestão. O relay roda a cada minuto, então o lag mínimo esperado fica entre 0 e 60 s: a meta de p95 < 60 s depende do relay não atrasar.
- **Zero perda:** Eventos aceitos pela API (o `events_accepted` do k6) = Eventos gravados com `attributes.load_run` = o `RUN_ID` da rodada, sem lote pendente ou com falha (`scripts/load_report.py`).

## Dimensionamento inicial

### Conexões

O `aid_db` usa `NullPool` (ADR-0009): o pool é o do Supavisor, em modo transação. No pior caso, cada requisição em curso abre uma conexão de cliente:

```text
clientes = api_max_instances × api_concurrency + workers × worker_max_instances × worker_concurrency
         = 4 × 40 + 5 × 3 × 8 = 280  ≤  supavisor_client_budget (300)
```

O projeto Supabase é compartilhado com o jayv-coder em produção: o Doctor fica com uma **fatia** dos clientes do Supavisor (`supavisor_client_budget`). O `check "conexoes_cabem_no_supavisor"` do Terraform barra o plano que passar dela, e o teste `dimensionamento_acima_do_supavisor_e_barrado` garante que a checagem existe.

O `pool_size` do Supavisor (conexões reais no Postgres) é configurado no painel do projeto, que pertence ao jayv-coder. Ele não muda sem acordo. Para o Doctor, o que pesa são as transações curtas (o worker de ingestão grava um lote por transação, e a API faz uma por requisição). Com transações de ~20 ms, 15 conexões reais atendem centenas de clientes.

### Cloud Run

| Serviço | Concorrência | Máx. instâncias | Por quê |
|---|---|---|---|
| API | 40 | 4 | 50 Usuários a ~1 requisição/s cabem em 2 instâncias; 4 deixam folga para o pico de ingestão (1 lote/s por Integração) |
| Workers (cada) | 8 | 3 | push do Pub/Sub com ack até 600 s; a ingestão de um lote de 200 Eventos leva centenas de ms |

Os valores são variáveis da stack (`api_max_instances`, `api_concurrency`, `worker_max_instances`, `worker_concurrency`). Os resultados da carga calibram os números.

### Compute do Supabase

A ingestão de 3× a premissa é ~300 mil linhas por dia em `doctor.events`, particionada por mês (ADR-0011). Com a retenção de 90 dias, isso dá ~27 milhões de linhas no pior caso. O pico de 200/s por 10 min soma 120 mil linhas. Uma instância **Small** (2 GB) é o ponto de partida, a confirmar com a CPU e o I/O medidos na rodada (Metrics API do Supabase, ticket #34). O add-on é do projeto inteiro: mudar de plano é decisão conjunta com o jayv-coder.

## Como rodar

```bash
export API_URL=https://api.staging… RUN_ID=carga-$(date +%Y%m%d-%H%M) SINCE=$(date -u +%FT%TZ)
INGESTION_TOKEN=aid_ing_… INTEGRATION_ID=… make load:ingestion
USER_JWTS=jwt1,jwt2 make load:read          # em staging, suba RATE_LIMIT_PER_MINUTE na rodada
USER_JWT=… INCIDENT_IDS=id1,id2 make load:diagnoses
SUPABASE_DB_URL=… make load:report          # sai com 1 se alguma meta não foi atingida
```

- Rode em **staging**, nunca no projeto de produção compartilhado com o jayv-coder.
- O rate limit da API é de 120 requisições/min por Usuário e por token; ele não é o que se mede. Na rodada de leitura, passe vários JWTs ou suba `RATE_LIMIT_PER_MINUTE` só durante o teste.
- Os Diagnósticos em `hybrid` chamam o LLM de verdade e consomem Cota e dinheiro; para medir só a plataforma, use `MODE=rules_only`.

## Resultados

| Rodada | Ambiente | Ingestão (perda, lag p95) | Leitura p95 | Erros | Diagnósticos | Ação |
|---|---|---|---|---|---|---|
| — | staging | a medir | a medir | a medir | a medir | — |

Cada meta não atingida vira um ticket, com o link na coluna Ação.
