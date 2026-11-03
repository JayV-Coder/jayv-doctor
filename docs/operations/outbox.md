# Outbox e relay

Toda mensagem para o Pub/Sub nasce em `doctor.outbox_messages`, na mesma transação do dado que a origina (ADR-0001). Nenhum serviço publica direto.

| Quem grava na outbox | Tópico |
|---|---|
| `doctor.finish_import` (Importação concluída) | `ingestion.raw` |
| Worker de ingestão (Importação processada) | `correlation.requested` |

O relay é o serviço `worker-relay`, com a mesma imagem dos workers e `WORKER_NAME=relay`. O Cloud Scheduler o chama a cada minuto (`POST /relay`, com OIDC). Cada rodada faz o seguinte:

1. pega até 100 mensagens pendentes por vez, com `FOR UPDATE SKIP LOCKED`, então dois relays juntos não publicam a mesma linha;
2. publica cada uma pela API REST do Pub/Sub, com `tenant_id` e `outbox_id` nos atributos, e só identificadores nos logs;
3. marca `published_at`, ou soma uma tentativa se o Pub/Sub recusou.

A entrega é pelo menos uma vez: se o commit falhar depois do publish, a mensagem sai de novo, e os consumidores são idempotentes. Mensagem com 10 tentativas para de ser tentada e fica na tabela para investigação.

```sql
-- Lag e pendências (o painel do ticket #34 vai ler o mesmo).
select topic, count(*) as pendentes, max(attempts) as tentativas, min(created_at) as mais_antiga
from doctor.outbox_messages where published_at is null group by topic;
```

Só o relay tem `roles/pubsub.publisher` nos tópicos. Os workers recebem por push autenticado e, depois de 5 falhas, a mensagem vai para a DLQ do tópico (`<tópico>.dlq`).

Localmente e no CI, o relay publica no emulador quando `PUBSUB_EMULATOR_HOST` está definido.
