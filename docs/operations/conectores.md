# Framework de Conectores

## Como uma Sincronização roda

```text
Cloud Scheduler (1/min) → worker-connectors POST /schedule
  Conectores ativos ou em falha com next_run_at vencido → outbox connector.sync (e next_run_at += intervalo)
relay → Pub/Sub connector.sync → worker-connectors
  claim: trava o Conector; Sincronização em curso há menos de 10 min → "busy"; mais antiga → "interrompida"
  credencial: doctor.get_connector_secret (Vault, só service_role, registrado na auditoria)
  runtime (aid_connectors.runtime.run_sync): coleta lote a lote, com timeout por lote e retry com backoff exponencial e jitter
  cada lote: ingestion_batches + outbox ingestion.raw + Checkpoint do Conector, numa transação
  → worker de ingestão (ticket #12): sanitiza, valida, deduplica por event_id e grava doctor.events
```

Se o worker cair no meio, a próxima Sincronização retoma do último Checkpoint gravado. O que a fonte mandar de novo, a deduplicação da ingestão descarta.

## Política de falhas

| Situação | Conector | Próxima tentativa |
|---|---|---|
| Sucesso | `active`, zera as falhas | depois de `sync_interval_seconds` (padrão 5 min) |
| Erro de autenticação | `paused` até uma ação humana: trocar a credencial (`doctor.put_connector_secret`) reativa na hora | nenhuma |
| Prazo da Sincronização (8 min) com lotes a coletar | mantém, com o Checkpoint gravado | em 1 min, do Checkpoint |
| Erro inesperado (bug, banco, credencial ausente) | conta como falha | como as falhas acima |
| 1ª e 2ª falha seguida | `active` | em 1 min |
| 3ª falha seguida em diante | `failing` | backoff de 5 min, dobrando até 1 h |

Dentro de uma Sincronização, timeout, 429 e erro temporário são repetidos até 5 vezes, com backoff. O `Retry-After` do provedor é respeitado até 60 s. Autenticação, configuração inválida e Checkpoint que não avança ou volta a um valor já visto (paginação quebrada) não são repetidos. Pausa ou desativação feitas durante a Sincronização continuam valendo no fim dela.

## Escrever um Conector

1. Implemente `aid_connectors.base.Connector`:
   - `provider` e `rate_limit`;
   - `validate_config`;
   - `test_connection`;
   - `collect`: gera `Batch(events, checkpoint)`, com os Eventos no Contrato v1 sem `integration_id`, que o runtime preenche.

   Erros do provedor sobem como `ConnectorError(kind, mensagem)`, e a mensagem nunca leva a credencial. O conector não faz retry nem guarda Checkpoint: isso é do runtime.
2. Gere `event_id` estável para o mesmo registro na fonte (UUIDv7 a partir do id de origem). É o que permite repetir uma coleta sem duplicar.
3. Herde `aid_connectors.testing.ConnectorContractTests` nos testes do conector. A suíte confere:
   - a configuração;
   - o teste de conexão;
   - os Eventos no contrato;
   - o Checkpoint serializável e que sempre avança;
   - que retomar não repete Eventos;
   - o `event_id` estável.
4. Registre a classe em `aid_connector_worker.sync.REGISTRY` e o `provider` na verificação de `doctor.connectors`.

O conector `fake` aceita falhas injetadas pela config (`fail: {page, kind, times}`, `hang_seconds`, `broken_pagination`) e serve aos testes.

## Credenciais

Ficam no Supabase Vault (ADR-0006), com o nome `doctor/connector/<id>`, porque o Vault é do projeto inteiro. A tabela guarda só o `secret_id`, que o cliente nem consegue ler. A leitura é só pela `service_role`, sem papel novo no banco compartilhado (ADR-0009), e cada acesso chama `doctor.record_audit`, que o ticket #28 vai implementar.

## Google Cloud Logging (`gcp`)

Config:

```json
{
  "project_id": "acme-integracoes",
  "auth": "impersonation",
  "service_account": "doctor-reader@acme-integracoes.iam.gserviceaccount.com",
  "services": ["orders-sync"],
  "min_severity": "WARNING",
  "filter": "jsonPayload.app=\"orders\"",
  "backfill_hours": 24,
  "requests_per_minute": 60
}
```

- **Acesso, preferencialmente sem chave (`impersonation`):** o cliente cria uma Service Account com `roles/logging.viewer` no projeto e concede à conta do `worker-connectors` da plataforma `roles/iam.serviceAccountTokenCreator` nela. A credencial do Conector fica sem uso; o assistente do ticket #16 manda `-`.
- **Com chave (`key`):** a credencial é o JSON da Service Account, guardado no Vault.
- **Coleta:** `entries.list` em ordem de `timestamp`, numa janela que vai do Checkpoint menos 30 s até agora menos 30 s. Os 30 s cobrem as entradas que chegam ao Logging atrasadas. O que repetir na sobreposição tem o mesmo `event_id` (derivado de `insertId` e `timestamp`) e a ingestão descarta. O primeiro backfill é de 24 h ou 7 dias.
- **Cota:** pausa entre páginas para não passar de `requests_per_minute` (60 por padrão, a cota de leitura do Logging). `RESOURCE_EXHAUSTED` vira 429 e o runtime espera 60 s.
- **Mapeamento:**
  - `trace` → `trace_id`;
  - `labels.execution_id` ou `jsonPayload.execution_id` → `execution_id`;
  - `httpRequest.status` → `error.http_status`;
  - `resource.labels.service_name` → `source.service`;
  - severidades do Logging para as cinco do contrato;
  - nanossegundos truncados em microssegundos.
- **Teste de conexão sem `logging.viewer`:** a mensagem diz qual permissão falta (`logging.logEntries.list`), em qual Service Account e em qual projeto.
- O enriquecimento com o Cloud Trace (opcional no ticket) fica para depois.
