# Alerta: workers sem processar por 10 min

**Disparo:** numa assinatura `<tópico>.push`, a mensagem mais antiga sem ack tem mais de 10 min (`pubsub.googleapis.com/subscription/oldest_unacked_message_age`). O `/admin/health` mostra também `ingestion_lag_seconds` e `diagnosis_queue_seconds`.

1. **O worker responde?** Cloud Run `worker-<nome>`: revisão saudável, instâncias e erros. Push recebendo 5xx ou 501 (handler ausente) não confirma a mensagem.
2. **Lento ou travado:** traces `pubsub <tópico>` com duração alta mostram a etapa (LLM, Storage, banco). No diagnóstico, um LLM lento segura a fila até o timeout de 600 s.
3. **Limite de instâncias:** com `worker_max_instances` atingido e fila crescendo, suba o limite respeitando a fatia do Supavisor (`docs/operations/capacity.md`; o `check` do Terraform barra o que não cabe).
4. **Banco:** `db_connections` perto do máximo, ou a CPU do Supabase alta: siga [supabase-cpu](supabase-cpu.md).
5. Depois de normalizar, a fila drena sozinha. Se mensagens forem para a DLQ, siga [dlq](dlq.md).
