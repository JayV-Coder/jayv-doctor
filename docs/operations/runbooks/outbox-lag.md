# Alerta: lag da outbox acima de 5 min

**Disparo:** a mensagem mais antiga da outbox (`doctor.outbox_messages`) está há mais de 5 min sem publicar (`custom.googleapis.com/aid/outbox_lag_seconds`). A mesma medida sai no `/admin/health`.

1. **O relay está rodando?** Cloud Scheduler `aid-outbox-relay` (a cada minuto) e os logs do `worker-relay`. Job pausado ou falhando é a causa mais comum.
2. **O Pub/Sub recusa?** Log `outbox: … HTTP 4xx`: tópico inexistente ou permissão do relay. `outbox_stuck` > 0 indica mensagens recusadas 10 vezes, que ficam na tabela para investigação:
   ```sql
   select topic, count(*), min(created_at) from doctor.outbox_messages
   where published_at is null and attempts >= 10 group by 1;
   ```
3. **Volume:** com milhares pendentes e o relay saudável, cada rodada drena por 40 s. Rode `POST /relay` à mão (com OIDC) para acelerar e confira o pool do Supavisor (`db_connections` no dashboard).
4. Depois de corrigir a causa, mensagens com `attempts >= 10` voltam com `update … set attempts = 0` numa janela combinada. Os consumidores são idempotentes.
