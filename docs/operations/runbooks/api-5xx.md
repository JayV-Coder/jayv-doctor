# Alerta: API com 5xx acima de 1%

**Disparo:** mais de 1% das respostas do serviço `api` em 5xx por 5 min (`run.googleapis.com/request_count`).

1. **Deploy recente?** Compare o início do alerta com a última revisão do Cloud Run. Se coincidir, volte o tráfego para a revisão anterior:
   ```bash
   gcloud run services update-traffic api --region southamerica-east1 --to-revisions <anterior>=100
   ```
2. **Banco:** `503 auth_unavailable` ou erros de conexão nos logs indicam Supabase ou Supavisor. Veja `db_connections` e a CPU do Supabase no dashboard (runbook [supabase-cpu](supabase-cpu.md)).
3. **Rota específica:** filtre os logs por `severity>=ERROR`; cada entrada tem `request_id` e o trace. O span mostra a etapa (banco, Storage, JWKS).
4. **Storage:** `503 storage_unavailable` vem do Supabase Storage (status.supabase.com).
5. Registre o incidente e a causa; o alerta fecha sozinho 30 min depois de normalizar.
