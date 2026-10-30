milestone: Sprint 2 — Ingestão
description: Semanas 3–4. Upload de logs JSON/CSV, ingestão por API e Pub/Sub, sanitização e HMAC, framework de conectores, conector GCP Cloud Logging e tela de conectores.

<!-- issue: 11 -->
title: Importação manual de logs JSON, NDJSON e CSV
labels: feature, frontend, backend, M03-ingestion, mobile, P0
---
## Contexto
O entregável 2 da v0.1 é "conecte um projeto GCP **ou importe logs manualmente**". A Importação manual é o caminho mais curto para o piloto avaliar incidentes históricos.

## História de usuário
Como **Analyst**, quero enviar um arquivo de logs exportado, para diagnosticar falhas de sistemas que ainda não têm Conector.

## Escopo
- Bucket privado `raw-logs` no Supabase Storage, com caminho `{tenant_id}/imports/{import_id}/{filename}`. Policy do Storage: escrita e leitura apenas quando `(storage.foldername(name))[1] = app.current_tenant_id()::text`.
- Upload direto do navegador com **URL assinada de upload** emitida pela API (`POST /api/v1/imports` retorna `upload_url` e `import_id`). Upload resumível (TUS) para arquivos acima de 6 MB.
- Limites: 50 MB por arquivo e formatos `.json`, `.ndjson`, `.csv` (checagem por extensão **e** por magic bytes e parse). Outros formatos são recusados.
- Tabela `imports (tenant_id, id, integration_id, filename, size_bytes, sha256, format, status check in ('uploaded','processing','done','failed','rejected'), total_lines, accepted, rejected, duplicates, secrets_removed, error, created_by, created_at)`.
- Tabela `raw_log_objects (tenant_id, id, storage_path, sha256, size_bytes, source check in ('import','connector','api'), expires_at)`.
- Ao concluir o upload (`POST /api/v1/imports/{id}/complete`), grava uma mensagem `ingestion.raw` na outbox. O worker de {{#12}} faz o parse em streaming.
- CSV: tela de mapeamento de colunas para o Contrato de evento, com sugestão automática por nome de coluna e mapeamento salvo por Integração.
- Linhas rejeitadas guardadas com o motivo (`import_rejections`), para download.
- Tela 13: área de upload, progresso em tempo real (Realtime em `imports`) e resultados.

## UI — Tela 13
```text
┌──────────────────────────┐
│ ← Importar logs          │
│ Integração [Pedidos ▾]   │
│ ┌ ⇪ Escolher arquivo ──┐ │
│ │ JSON, NDJSON, CSV 50MB│ │
│ └──────────────────────┘ │
│ sap-order….ndjson [Norm.]│
│ ████████░░ 8.120/12.600  │
│ bapi-errors.csv [Concl.] │
│ 2.004 ev · 14 rej · 3 seg│
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** um arquivo `.xml`, **quando** enviado, **então** a importação fica `rejected` com a mensagem "Formato não permitido".
- **Dado** o mesmo arquivo (mesmo sha256) enviado duas vezes para a mesma Integração, **então** a segunda importação é marcada como duplicada e não gera Eventos novos.
- **Dado** um arquivo de 12 mil linhas, **quando** processado, **então** o progresso atualiza ao menos a cada 2 s na tela.
- **Dado** um usuário do tenant B, **quando** tenta ler o objeto de A no Storage, **então** recebe `403`.

## Segurança / LGPD
- O Log bruto expira conforme a retenção (30 dias padrão, {{#29}}) e não aparece em listagens públicas.
- O conteúdo passa pela Sanitização ({{#13}}) **antes** de virar Evento.

## Testes
- Fixtures CSV e NDJSON com linhas inválidas, encoding latin-1 e BOM.
- Teste de isolamento das policies do Storage.

## Dependências
{{#08}}, {{#10}}

<!-- issue: 12 -->
title: Pipeline de ingestão (POST /ingestion/events, outbox, Pub/Sub, worker de normalização idempotente)
labels: feature, backend, infra, M03-ingestion, P0
---
## Contexto
O checklist de liberação exige "ingestão idempotente e sem perda silenciosa de eventos". O Pub/Sub não é transacional com o Postgres, então usamos outbox ([ADR-0001]({{repo}}/docs/adr/0001-supabase-como-plataforma-de-dados.md)).

## Escopo
- **Tokens de ingestão** para sistemas externos: `ingestion_tokens (tenant_id, id, name, integration_id, token_hash, last_used_at, revoked_at)`. O header é `Authorization: Bearer aid_ing_…`, e o `tenant_id` é derivado do token, nunca do payload.
- `POST /api/v1/ingestion/events`: lote de até 500 Eventos ou 1 MB. Valida contra o Contrato v1 e responde `202 {accepted, rejected:[{index, reason}]}`. O lote bruto vai para o Storage e a mensagem para a outbox.
- Tabela `outbox_messages (id bigserial, tenant_id, topic, payload jsonb, created_at, published_at, attempts)`. O worker `outbox-relay` publica com `FOR UPDATE SKIP LOCKED` e marca `published_at`.
- **Worker `ingestion`** (consome `ingestion.raw`):
  1. lê o Log bruto;
  2. faz o parse;
  3. mapeia para o Contrato v1;
  4. aplica a Sanitização ({{#13}});
  5. deduplica;
  6. grava `events`;
  7. publica `correlation.requested`.
- Tabela `events` **particionada por mês** (`pg_partman`, `timestamp`), com colunas do Contrato v1 mais `tenant_id`, `raw_log_object_id`, `ingested_at` e `dedup_key`. A `dedup_key` é o sha256 de (`tenant_id`, `source`, `event_id` ou hash do conteúdo canônico) e tem `unique (tenant_id, dedup_key, timestamp)`.
- Índices: `(tenant_id, execution_id)`, `(tenant_id, trace_id)`, `(tenant_id, integration_id, timestamp desc)` e `(tenant_id, business_reference)`.
- Idempotência no worker: mensagens repetidas não duplicam (`insert … on conflict do nothing`). Um ack só acontece após o commit.
- Métricas: eventos aceitos, rejeitados e duplicados por tenant; lag da outbox; mensagens na DLQ.

## Critérios de aceite
- **Dado** o mesmo lote enviado 3 vezes, **então** a tabela `events` tem exatamente uma cópia de cada Evento.
- **Dado** um worker que cai depois de gravar e antes de dar ack, **quando** a mensagem é reentregue, **então** não há duplicação.
- **Dado** um token revogado, **então** `401`. Um payload com `tenant_id` responde `422`.
- **Dado** um teste de carga de 100 mil eventos em 1 h no staging, **então** não há perda e o lag p95 fica abaixo de 60 s (a medição completa está em {{#33}}).

## Testes
- Testes de integração com o emulador do Pub/Sub. Chaos test que mata o worker no meio do lote.
- Isolamento: o token do tenant A não grava Eventos em B, nem com `integration_id` de B (a FK composta impede).

## Dependências
{{#07}}, {{#08}}, {{#11}}

<!-- issue: 13 -->
title: Sanitização de segredos e dados pessoais + Referências de negócio com HMAC por tenant
labels: feature, backend, security, lgpd, M03-ingestion, P0
---
## Contexto
O PRD §8 exige remover tokens, senhas, dados pessoais e segredos **antes da persistência analítica e do envio ao LLM**. Também exige transformar identificadores comerciais em HMAC por tenant.

## Escopo
- Pacote `packages/security` com a interface profunda `Sanitizer.sanitize(record) -> (record, report)`:
  - detectores: Bearer, JWT, chaves AWS, GCP e Salesforce, `password=`, cabeçalhos `Authorization` e `Cookie`, cartões (Luhn), **CPF/CNPJ (com dígito verificador)**, e-mail, telefone BR e IPs (configurável);
  - substituição por `[REMOVIDO:<tipo>]`;
  - `report` com contagem por tipo, gravado no Evento (`sanitization_report`).
- Limites: string de até 8 KB por campo e profundidade de JSON até 10; acima disso, trunca com marcador.
- **HMAC de Referência de negócio:** a chave por tenant é derivada por HKDF da chave mestre do Secret Manager com o `tenant_id`; o formato é `hmac:<hex16>`. Configuração por Integração define quais campos são Referências (ex.: `order_id`, `customer_document`).
- Função de busca: a API aplica o HMAC ao termo digitado (ex.: número do pedido) para permitir a busca exata sem guardar o valor.
- Regras de Sanitização configuráveis por tenant (adicionar padrões, liberar IPs internos).

## Critérios de aceite
- **Dado** um log com `Authorization: Bearer eyJ…`, **então** o Evento persistido contém `[REMOVIDO:bearer]` e o relatório conta 1.
- **Dado** o pedido `4500012345` nos tenants A e B, **então** os HMACs são diferentes, e no mesmo tenant são estáveis.
- **Dado** um CPF inválido (dígito errado), **então** não é removido, para evitar falso positivo em IDs numéricos.
- Desempenho: 10 mil registros por segundo por núcleo no benchmark.

## Testes
- Corpus de 200 casos positivos e negativos (`packages/security/tests/corpus`), com precisão de 100% nos segredos e recall ≥ 99% em PII no corpus.
- Fuzzing com Hypothesis: o Sanitizer nunca lança exceção e nunca aumenta o tamanho além do marcador.

## Dependências
{{#08}}

<!-- issue: 14 -->
title: Framework de conectores (interface Connector, Sincronizações, Checkpoints, retries, Vault)
labels: feature, backend, database, security, M02-connectors, P0
---
## Contexto
O PRD §10 pede que "conectores implementem contratos comuns de autenticação, coleta, checkpoint e tratamento de falhas". As credenciais ficam no Vault ([ADR-0006]({{repo}}/docs/adr/0006-vault-para-credenciais-de-conectores.md)).

## Escopo
- `packages/connectors/base`, com um **módulo profundo** e interface pequena:
  ```python
  class Connector(Protocol):
      provider: ClassVar[str]
      def validate_config(self, config: dict) -> ConfigErrors: ...
      async def test_connection(self, creds: Secret, config: dict) -> TestResult: ...
      async def collect(self, creds, config, checkpoint: Checkpoint | None) -> AsyncIterator[Batch]: ...
      rate_limit: RateLimitPolicy
  ```
  O runtime (fora do conector) cuida de retries com backoff exponencial e jitter, circuit breaker, timeouts, persistência de Checkpoint por lote e métricas.
- Tabelas:
  - `connectors (tenant_id, id, integration_id, provider, name, config jsonb, secret_id uuid, status check in ('active','paused','failing','disabled'), consecutive_failures, last_sync_at, last_error, next_run_at)`;
  - `connector_syncs (tenant_id, id, connector_id, started_at, finished_at, status, checkpoint_from, checkpoint_to, records, error)`.
- Vault: `app.put_connector_secret(connector_id, secret)` e `app.get_connector_secret(connector_id)` são `security definer`. O `get` só é executável pelo papel `connector_worker` e registra o acesso na auditoria.
- Agendador: `pg_cron` a cada minuto enfileira `connector.sync` para conectores com `next_run_at <= now()`, com advisory lock para nunca rodar duas Sincronizações do mesmo Conector ao mesmo tempo.
- Worker `connectors`: executa a Sincronização e grava os lotes como Logs brutos, que seguem o mesmo pipeline do {{#12}}.
- Política de falhas: 3 falhas seguidas mudam o status para `failing` e reagendam com backoff até 1 h. Um erro de autenticação muda para `paused` até uma ação humana.
- API:
  - `POST /api/v1/connectors` (credencial vai direto para o Vault e nunca volta em respostas);
  - `GET`/`PATCH /api/v1/connectors`;
  - `POST /api/v1/connectors/{id}/test`, `/sync`, `/pause`, `/resume`;
  - `GET /api/v1/connectors/{id}/syncs`.
- Conector fake (`provider = 'fake'`) para testes.

## Critérios de aceite
- **Dado** um worker que cai no meio de uma Sincronização, **quando** reinicia, **então** retoma do último Checkpoint sem perder nem duplicar (a dedup do {{#12}} cobre a sobreposição).
- **Dado** `GET /connectors/{id}`, **então** nenhuma resposta contém a credencial, nem mascarada.
- **Dado** o papel `authenticated`, **quando** chama `app.get_connector_secret`, **então** `permission denied`.

## Testes
- Suíte de contrato reutilizável (`ConnectorContractTests`) que todo conector novo deve passar.
- Conector fake com falhas injetadas: timeout, 429, 401 e paginação quebrada.

## Dependências
{{#07}}, {{#12}}, {{#13}}

<!-- issue: 15 -->
title: Conector Google Cloud Logging (P0)
labels: feature, backend, M02-connectors, P0
---
## Contexto
É o primeiro conector do PRD §5 e o primeiro mercado (empresas que executam integrações no GCP).

## Escopo
- `packages/connectors/gcp` implementando `Connector`:
  - credencial: JSON de Service Account (no Vault) ou, preferencialmente, **Workload Identity Federation / impersonation** de uma SA do cliente que concede `roles/logging.viewer` à SA da plataforma (sem chave);
  - `collect`: `entries.list` com filtro `timestamp >= checkpoint AND timestamp < now()-30s`, ordenado por timestamp, com `pageToken`;
  - Checkpoint = (último timestamp, último `insertId`), com janela de sobreposição de 30 s;
  - filtros configuráveis: serviços do Cloud Run, `severity >= X` e consulta avançada do Logging;
  - mapeamento para o Contrato v1:
    - `trace` → `trace_id`;
    - `labels.execution_id` / `jsonPayload.execution_id` → `execution_id`;
    - `httpRequest.status` → `error.http_status`;
    - `resource.labels.service_name` → `source.service`;
  - cotas: respeita a cota de leitura da API (60 req/min por projeto, configurável), com backoff em `RESOURCE_EXHAUSTED`.
- Backfill inicial configurável (24 h ou 7 dias).
- Opcional atrás de feature flag: enriquecimento com o Cloud Trace (spans do `trace_id`).

## Critérios de aceite
- **Dado** um projeto com 50 mil entradas por dia, **quando** sincroniza a cada minuto, **então** não perde entradas (comparação com a contagem do próprio Logging) e não estoura a cota.
- **Dado** uma SA sem `logging.viewer`, **quando** testa a conexão, **então** a mensagem diz exatamente qual permissão falta.
- **Dado** o checkpoint em T, **quando** a Sincronização retoma, **então** pede a partir de T−30 s e deduplica.

## Testes
- Testes com respostas gravadas (VCR) da API do Logging. Contrato do {{#14}}.
- Teste E2E em staging contra um projeto GCP de teste com logs sintéticos.

## Dependências
{{#14}}

<!-- issue: 16 -->
title: Tela de gerenciamento de Conectores e wizard do GCP
labels: feature, frontend, M02-connectors, mobile, P0
---
## Contexto
O PRD §9 descreve "Gerenciamento de conectores: configuração, permissões, status, última sincronização, erros e teste de conectividade".

## História de usuário
Como **Admin**, quero ver pelo celular se a coleta está saudável e corrigir uma permissão faltante sem abrir o console do GCP.

## Escopo
- **Tela 11 (lista):** cards por Conector com status (Saudável, Com falhas, Pausado), última Sincronização, Checkpoint, contagem do último lote, botões "Testar conexão" e "Sincronizar", e card de Importação manual.
- **Tela 12 (wizard GCP, 4 passos):**
  1. projeto;
  2. método de credencial (impersonation recomendado, com instruções `gcloud` copiáveis, ou upload de JSON);
  3. filtros e intervalo, com pré-visualização ("48 registros na última hora");
  4. vincular Integração e ativar.
- Detalhe do Conector: histórico de Sincronizações (lista com status e duração) e último erro com a mensagem acionável.
- Atualização em tempo real do status (Realtime em `connectors`).
- Card "Salesforce · SAP — v0.2" desabilitado.

## UI — Telas 11 e 12
```text
┌──────────────────────────┐
│ Conectores   [Adicionar] │
│ ┌ GCP acme-integ [Saudá]┐│
│ │ há 2 min · 1.204 ev   ││
│ │ [Testar] [Sincronizar]││
│ └───────────────────────┘│
│ ┌ GCP acme-hml [Falhas] ┐│
│ │ ⚠ PERMISSION_DENIED … ││
│ └───────────────────────┘│
│ Início Inc Exec [Con] +  │
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** um Analyst, **então** vê a lista mas não vê "Adicionar", "Sincronizar" nem "Editar".
- **Dado** um teste de conexão com falha, **então** a mensagem mostra a causa e a ação ("Conceda roles/logging.viewer…").
- O wizard funciona inteiro em 390 px e mantém o progresso se o usuário sair e voltar (rascunho em `sessionStorage`).

## Testes
- Playwright mobile do wizard completo contra o conector fake.

## Dependências
{{#09}}, {{#15}}
