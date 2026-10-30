---
status: accepted
---
# Supabase como plataforma de dados, GCP como computação

O PRD original previa Cloud SQL, OIDC próprio, Cloud Storage, Secret Manager e SSE. Decidimos usar o **Supabase (região São Paulo)** como base de dados e identidade: Postgres (com pgvector, pg_cron e pg_partman), Auth, Storage, Realtime e Vault. O GCP (`southamerica-east1`) fica com a computação: Cloud Run para a API FastAPI e os workers, Pub/Sub e Terraform. O motivo é que Auth, RLS, Storage e Realtime, integrados ao mesmo Postgres, eliminam boa parte da fundação que o PRD mandava construir, e o Cloud Run e o Pub/Sub continuam melhores para 100 mil eventos/dia e chamadas longas de LLM.

## Considered Options
- **Só o Postgres do Supabase**: perde o principal ganho (Auth + RLS integrados).
- **Supabase inteiro, incluindo Queues e Edge Functions**: os limites de tempo e de runtime das Edge Functions não servem a workers Python de diagnóstico.

## Consequences
- O Pub/Sub não participa de transações do Postgres. A publicação de mensagens passa por uma tabela outbox (`outbox_messages`) drenada por um worker.
- Os segredos da plataforma (chaves de LLM, chave HMAC mestre) ficam no Secret Manager. As credenciais de conectores dos clientes ficam no Vault (ADR-0006).
