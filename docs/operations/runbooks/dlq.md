# Alerta: DLQ com mensagens

**Disparo:** uma assinatura `<tópico>.dlq.pull` com mensagem por mais de 5 min. Uma mensagem só chega à DLQ depois de 5 entregas recusadas pelo worker.

1. Ache o tópico no alerta (`subscription_id`) e o worker que o consome (`infrastructure/terraform/stack/main.tf`, `local.topics`).
2. Logs do worker no horário (Cloud Logging, bucket `aid-services`), filtrando por `jsonPayload.topic` e `severity>=ERROR`. Os logs trazem só ids (`message_id`, `tenant_id`), nunca o payload.
3. Abra o trace da mensagem: o log tem `logging.googleapis.com/trace`, e o span `pubsub <tópico>` mostra onde falhou.
4. **Erro de código ou de dado:** corrija, publique e reprocesse:
   ```bash
   gcloud pubsub subscriptions pull <tópico>.dlq.pull --limit=10 --format=json > dlq.json   # confira antes
   # republique no tópico original e só então confirme (ack) na DLQ
   ```
   Os handlers são idempotentes: reprocessar não duplica.
5. **Mensagem que nunca vai passar** (Integração apagada, por exemplo): confirme na DLQ e registre no ticket do incidente.
6. `/admin/health` (relay) e o dashboard "plataforma" confirmam a volta ao normal.
