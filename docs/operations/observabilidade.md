# Observabilidade da plataforma

Ticket #34. A plataforma avisa quando ela própria falha, antes do cliente perceber.

## Traces de ponta a ponta

```text
cliente ─traceparent─▶ API (span HTTP) ─doctor.traceparent─▶ outbox (coluna traceparent)
  ─▶ relay (atributo traceparent no Pub/Sub) ─▶ worker (span "pubsub <tópico>")
  ─▶ ingestão (span "doctor.events insert")
```

- A API (`tenant_tx`, `anonymous_tx`) e os workers (`platform_role`, `tenant_role`) põem o `traceparent` do span atual na sessão. O trigger `outbox_messages_traceparent` grava o valor em cada mensagem, inclusive nas que as funções do banco criam.
- O relay publica o valor como atributo da mensagem, e o runtime dos workers abre o span da mensagem como filho dele. O teste `workers/runtime/tests/test_trace_end_to_end.py` comprova o critério de aceite: um Evento injetado na API chega à gravação em `doctor.events` num único trace.
- Exportação para o Cloud Trace com `OTEL_ENABLED=true` (API e workers, no Terraform).

## Logs

JSON na saída padrão (`aid_observability.logs`), com `severity`, `request_id`, `tenant_id`, `topic`, `message_id`, `worker` e a ligação ao trace (`logging.googleapis.com/trace`). Só esses campos entram, nunca payload, e-mail ou Referência, e o traceback perde os `[parameters: …]` do SQLAlchemy. Os logs ficam no bucket `aid-services`, em southamerica-east1, por 30 dias.

## Métricas

| Métrica | De onde |
|---|---|
| lag e pendentes da outbox, travadas | `doctor.platform_health()` → `custom.googleapis.com/aid/*`, a cada minuto (worker de diagnóstico) |
| lag e lotes da ingestão, Conectores em `failing`, Sincronizações p95 | idem |
| Diagnósticos na fila, p95 da última hora, falha e tokens do LLM | idem |
| conexões no Postgres | idem (`pg_stat_activity`) |
| CPU e disco do Supabase | Metrics API do Supabase (`/customer/v1/privileged/metrics`), pela chave de serviço |
| DLQ e mensagem mais antiga sem ack | Pub/Sub (nativas) |
| taxa de erro e latência da API | Cloud Run (nativas) |

O tempo por etapa de um Diagnóstico fica no trace (`pubsub diagnosis.requested`) e na coluna `stage`. A métrica guarda o total.

## Alertas

Todos vão para o e-mail do plantão (`alert_emails`) e, se configurado, para o canal de plantão (`oncall_webhook_url`). Cada um aponta para o seu runbook:

| Alerta | Limite | Runbook |
|---|---|---|
| DLQ com mensagens | > 0 por 5 min | [dlq](runbooks/dlq.md) |
| Lag da outbox | > 5 min | [outbox-lag](runbooks/outbox-lag.md) |
| API com 5xx | > 1% por 5 min | [api-5xx](runbooks/api-5xx.md) |
| Workers sem processar | mensagem sem ack > 10 min | [workers-parados](runbooks/workers-parados.md) |
| CPU do Supabase | > 80% por 15 min | [supabase-cpu](runbooks/supabase-cpu.md) |
| Erro do LLM | > 10% na última hora | [llm-erros](runbooks/llm-erros.md) |

O dashboard "Integration AI Doctor · plataforma" fica versionado no Terraform (`modules/observability`).

## Status interno

`GET /admin/health` no `worker-relay`: as medidas de `platform_health()` com os mesmos limites dos alertas (`aid_observability.health`), `status` `ok` ou `degraded` e o runbook de cada medida fora do limite. O relay é interno e só aceita chamada com IAM (`platform_operators`); nenhum tenant chega lá. Os números são de todas as Organizações juntas, sem `tenant_id`.

```bash
gcloud run services proxy worker-relay --region southamerica-east1 --port 8081 &
curl -s localhost:8081/admin/health | jq .status
```
