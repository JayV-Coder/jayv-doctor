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
Supabase (Postgres + pgvector, Auth, Storage, Realtime, Vault) · Python 3.12 + FastAPI · Cloud Run + Pub/Sub · Next.js + TypeScript + Tailwind + shadcn/ui (PWA) · Claude / Vertex AI · Terraform.

## Criar as issues no GitHub
```bash
gh auth login
python3 scripts/create-github-issues.py --dry-run   # valida
python3 scripts/create-github-issues.py             # cria labels, milestones, 53 issues + índice
```
