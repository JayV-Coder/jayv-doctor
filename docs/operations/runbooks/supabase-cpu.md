# Alerta: CPU do Supabase acima de 80% por 15 min

**Disparo:** `custom.googleapis.com/aid/supabase_cpu_utilization` > 0,8 por 15 min, lida da Metrics API do Supabase a cada minuto pelo worker de diagnóstico. **O projeto é compartilhado com o jayv-coder (ADR-0009):** a carga pode ser dele.

1. **Quem está consumindo?** No painel do Supabase (Query Performance) ou:
   ```sql
   select usename, application_name, state, count(*) from pg_stat_activity group by 1, 2, 3 order by 4 desc;
   select query, calls, mean_exec_time from pg_stat_statements order by total_exec_time desc limit 10;
   ```
   Consultas fora do schema `doctor` são do jayv-coder: avise o time dele antes de qualquer ação.
2. **Do Doctor:** picos de ingestão (`ingestion_batches_pending`), a purga diária (03:00 BRT) ou o agregado do Dashboard (a cada 10 min). Reduza `worker_max_instances` da ingestão para aliviar, aceitando lag maior.
3. **Persistente:** subir o compute add-on é do projeto inteiro: decisão conjunta com o jayv-coder (`docs/operations/capacity.md`).
4. `supabase_metrics_up = 0` no dashboard significa que a medida parou de chegar (chave ou Metrics API): o alerta fica sem dado, não "ok".
