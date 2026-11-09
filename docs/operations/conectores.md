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

## SAP Integration Suite (`sap`, ticket #38)

Lê os Message Processing Logs do Cloud Integration (`/api/v1/MessageProcessingLogs`, OData v2). Só lê: a service key precisa do papel de leitura de monitoração (`MonitoringDataRead`).

```json
{
  "product": "integration_suite",
  "api_url": "https://acme.it-cpi018.cfapps.br10.hana.ondemand.com",
  "token_url": "https://acme.authentication.br10.hana.ondemand.com/oauth/token",
  "include_completed": false,
  "backfill_hours": 24,
  "page_size": 200,
  "requests_per_minute": 60
}
```

- **Credencial:** a service key do plano `api` do Process Integration Runtime, `{"client_id", "client_secret"}` no Vault, trocada por token com OAuth client credentials. Token e API só em hosts da SAP BTP (`*.hana.ondemand.com`, `*.cloud.sap`), com HTTPS e sem usuário na URL (SSRF); endereço local só com `AID_SAP_ALLOW_LOOPBACK=1`, que existe só no E2E. Resposta fora do formato esperado vira erro temporário classificado.
- **Eventos:** `FAILED`, `ESCALATED` e `RETRY` (e `COMPLETED` com `include_completed`), um por mensagem.
  - `execution_id` = `CorrelationId`: a Execução junta os passos do iFlow e o que veio antes e depois dele;
  - `operation` e `source.resource` = o iFlow;
  - `error.message` = o `CustomStatus`;
  - atributos com o Guid, o status, o sender e o receiver.
- **Checkpoint:** `(LogEnd, MessageGuid)`, com desempate pelo Guid no mesmo instante, por `$filter`/`$orderby`/`$top`.
- **Ainda não:** o detalhe do erro (`ErrorInformation/$value`) exige uma chamada por mensagem e fica para quando o volume do piloto mostrar a necessidade. O conector OData genérico para enriquecimento por Referência vai com o ticket #40. O assistente na tela fica para depois do piloto; por enquanto, o Conector se cria pela API.

## Google Cloud Logging (`gcp`)

Config:

```json
{
  "project_id": "acme-integracoes",
  "auth": "key",
  "services": ["orders-sync"],
  "min_severity": "WARNING",
  "filter": "jsonPayload.app=\"orders\"",
  "backfill_hours": 24,
  "requests_per_minute": 60
}
```

- **Acesso (`key`):** o cliente cria uma Service Account com `roles/logging.viewer` no projeto, e a credencial do Conector é o JSON da chave dela, guardado no Vault. O `token_uri` do JSON é ignorado: o token sai sempre de `oauth2.googleapis.com`.
- **Sem chave (`impersonation`, preferido no ticket): desligado por enquanto.** Com uma só conta de plataforma, uma Organização poderia nomear a Service Account de outra Organização, que deu permissão àquela conta, e ler os logs dela (confused deputy). Para ligar, cada Organização precisa da própria identidade de plataforma: uma Service Account por Organização, criada no onboarding do Conector, que o cliente autoriza. Isso exige a sessão de configuração do GCP e está em `docs/operations/pendencias.md`.
- **Coleta:** `entries.list` em ordem de `timestamp`, numa janela que vai do Checkpoint menos 30 s até agora menos 30 s. Os 30 s cobrem as entradas que chegam ao Logging atrasadas. O que repetir na sobreposição tem o mesmo `event_id` (derivado de `insertId` e `timestamp`) e a ingestão descarta. O primeiro backfill é de 24 h ou 7 dias.
- **Cota:** pausa entre chamadas, também entre tentativas da mesma Sincronização, para não passar de `requests_per_minute` (60 por padrão, a cota de leitura do Logging). `RESOURCE_EXHAUSTED` vira 429 e o runtime espera 60 s. O token é reaproveitado até vencer.
- **Consulta avançada (`filter`):** entra entre parênteses, e é recusada se tiver parênteses desbalanceados fora de aspas: assim não consegue escapar da janela de tempo.
- **Mapeamento:**
  - `trace` → `trace_id`;
  - `labels.execution_id` ou `jsonPayload.execution_id` → `execution_id`;
  - `httpRequest.status` → `error.http_status`;
  - `resource.labels.service_name` → `source.service`;
  - severidades do Logging para as cinco do contrato;
  - nanossegundos truncados em microssegundos.
- **Teste de conexão sem `logging.viewer`:** a mensagem diz qual permissão falta (`logging.logEntries.list`), em qual Service Account e em qual projeto. Com a API do Logging desativada, a mensagem diz isso, e não manda conceder papel.
- **Prévia:** o teste antes de salvar (`POST /connectors/test`, usado pelo assistente) lê uma página (até 1.000 entradas) da última hora com os filtros e diz quantas atendem ("48 registros na última hora…", ou "Mais de 1.000…"). O teste de um Conector salvo lê uma entrada só: prova o acesso sem gastar a cota do cliente.
- **E2E:** `AID_GCP_OAUTH_URL` e `AID_GCP_LOGGING_URL` apontam o conector para o GCP falso de `apps/web/e2e/fake-gcp.mjs`. Só aceitam endereço de loopback: num ambiente real, uma delas esquecida derruba o Conector em vez de mandar o JWT assinado e os tokens dos clientes para outro host. O Terraform não as define.
- O enriquecimento com o Cloud Trace (opcional no ticket) fica para depois.

## Tela (ticket #16)

- **Tela 11** (`/conectores`): um card por Conector com status (Saudável, Aguardando, Com falhas, Pausado, Desativado), última Sincronização com a contagem de eventos, Checkpoint e, com falhas, o último erro e a próxima tentativa. Todo Papel vê; só Owner e Admin com MFA veem "Adicionar", "Testar conexão", "Sincronizar", "Retomar", "Pausar", "Editar" e "Trocar credencial".
- **Testar conexão de um Conector salvo** pede a credencial de novo: a salva não sai do Vault. A enviada serve só ao teste.
- **Tela 12** (`/conectores/novo`): projeto, credencial (com os comandos `gcloud` copiáveis), filtros com prévia, Integração e ativação. O rascunho fica no `sessionStorage` sem a credencial; quem volta no meio cai no passo da credencial e envia a chave de novo.
- **Tempo real:** `doctor.connectors` está na publicação `supabase_realtime`. A tela só usa o aviso para buscar de novo na API; o evento passa pelo RLS e pelos privilégios de coluna, então não traz `secret_id`.
