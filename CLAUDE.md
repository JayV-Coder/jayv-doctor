# Integration AI Doctor

SaaS B2B que diagnostica falhas de integrações (SAP, Salesforce, GCP). Supabase (Postgres, Auth, Storage, Realtime, Vault) + FastAPI/workers no Cloud Run + Next.js PWA mobile first.

## Antes de agir
- **Vocabulário** (Organização, Execução, Incidente, Diagnóstico, Evidência…): [GLOSSARY.md](GLOSSARY.md). Use esses termos em código, UI e issues.
- **Implementando um ticket**: leia a issue e o arquivo-fonte em [docs/backlog/](docs/backlog/); a Definition of Done está em [docs/backlog/README.md](docs/backlog/README.md).
- **Decisão arquitetural que parece estranha**: procure o porquê em [docs/adr/](docs/adr/) antes de "corrigir".
- **Tela nova ou alterada**: siga o mockup correspondente (link em [docs/mockups/README.md](docs/mockups/README.md)) e projete primeiro para 390 px.
- **Tabela nova**: siga `supabase/CONVENTIONS.md`.

## Invariantes
- O `tenant_id` vem só do JWT (claim do Custom Access Token Hook) ou da identidade do conector; payload externo nunca o define.
- Toda tabela de tenant: `tenant_id`, `unique (tenant_id, id)`, FKs compostas, RLS e teste de isolamento.
- A API acessa dados dentro de `tenant_tx(claims)`, com o RLS valendo; `service_role` fica restrita a jobs de plataforma.
- Logs e documentos de clientes chegam ao LLM sanitizados e delimitados como dados não confiáveis; Recomendações são sempre ações humanas.
- Diagnóstico publicado é imutável; nova análise = nova versão. Toda Evidência aponta para um registro real do mesmo tenant.
- Confiança é exibida sempre como "heurística".

## Fluxo de trabalho
Teste primeiro (`/tdd`), migração em `supabase/migrations`, tipos regenerados, revisão com `/code-review`.
