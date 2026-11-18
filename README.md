# Integration AI Doctor

Plataforma SaaS B2B que coleta, correlaciona e diagnostica falhas em integrações corporativas (SAP, Salesforce, Google Cloud), com regras determinísticas, RAG e LLM, apresentando causas prováveis com evidências verificáveis.

**Status:** planejamento. Ainda sem código; o backlog define a construção.

| Documento | Conteúdo |
|---|---|
| [docs/prd.md](docs/prd.md) | PRD e arquitetura técnica v1.1 (Supabase) |
| [GLOSSARY.md](GLOSSARY.md) | Linguagem do domínio |
| [docs/adr/](docs/adr/) | Decisões de arquitetura |
| [docs/mockups/](docs/mockups/) | Mockups mobile first (26 telas) |
| [docs/backlog/](docs/backlog/) | 53 tickets em 10 milestones (Sprint 1 → v1.0) |

## Stack
Supabase (Postgres + pgvector, Auth, Storage, Realtime, Vault) · Python 3.12 + FastAPI · Cloud Run + Pub/Sub · app no site da JayV (Next.js, `/doctor` em JayV-Coder/site — ADR-0023) · Claude / Vertex AI · Terraform.

## Desenvolvimento
Requisitos: Node 22 com pnpm 9 (`corepack enable`), [uv](https://docs.astral.sh/uv/) e GNU make. Docker e Supabase CLI são necessários a partir do ticket #2.

```bash
cp .env.example .env
make dev-setup   # submódulo do banco (ADR-0022), pnpm install, uv sync, hooks de pre-commit
make check       # lint + typecheck + testes (o mesmo que o CI)
```

| Pasta | Conteúdo |
|---|---|
| `apps/api` | FastAPI; o app fica no site da JayV (JayV-Coder/site, `/doctor`, ADR-0023) |
| `vendor/supabase` | submódulo `JayV-Coder/supabase`: migrações (`*_doctor_*`) e testes de banco (`tests/doctor/`) |
| `workers/*` | ingestion, correlation, diagnosis, connectors, retention |
| `packages/*` | contracts, connectors, diagnosis-engine, knowledge, security |
| `supabase/` | migrações, seed e testes pgTAP |
| `infrastructure/terraform` | GCP |
| `tests/*` | integração, segurança, avaliação, carga |

As telas do Doctor ficam no site da JayV (JayV-Coder/site, `/[locale]/doctor`, ADR-0023), que fala com esta API pelo servidor (`DOCTOR_API_URL`). Os testes de integração da API e dos workers rodam contra a stack local (`supabase start`) com `INTEGRATION_DB_URL`.

Pacotes TS são workspaces pnpm (orquestrados pelo Turborepo). Pacotes Python são membros do workspace uv em `pyproject.toml`; nomes de arquivos de teste Python são únicos no repositório.

## Criar as issues no GitHub
```bash
gh auth login
python3 scripts/create-github-issues.py --dry-run   # valida
python3 scripts/create-github-issues.py             # cria labels, milestones, 53 issues + índice
```
