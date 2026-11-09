# Alerta: medidas da plataforma sem chegar

**Disparo:** `custom.googleapis.com/aid/outbox_lag_seconds` sem ponto há 10 min, ou a Metrics API do Supabase sem responder por 15 min (`supabase_metrics_up < 1`). Sem dado, os alertas de limite (outbox, filas, LLM, CPU) **não disparam**: este é o alarme do próprio monitoramento.

1. **Job de métricas:** Cloud Scheduler `aid-platform-metrics` (a cada minuto) e os logs do `worker-diagnosis` em `/platform/metrics`. Falha no banco ou no Cloud Monitoring (400 de descritor, permissão `monitoring.metricWriter`) aparece ali.
2. **Metrics API do Supabase** (`supabase_metrics_up = 0`): chave de serviço rotacionada ou endpoint fora do ar. As outras medidas continuam chegando; só a CPU e o disco ficam sem dado.
3. Enquanto durar, acompanhe pelo `/admin/health` do relay (lê o banco direto) e pelo dashboard do Supabase.
