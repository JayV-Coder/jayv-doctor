# Backlog — Integration AI Doctor

São 54 tickets: 53 funcionalidades e 1 índice. Cada arquivo `NN-*.md` corresponde a uma milestone e contém os tickets dela, na ordem de criação, que segue as dependências.
Para criar tudo no GitHub (labels, milestones e issues), use [`scripts/create-github-issues.py`](../../scripts/create-github-issues.py).

## Formato dos arquivos

```text
<!-- issue: 07 -->
title: Título do ticket
labels: feature, backend, M01-org, P0
---
Corpo em Markdown…
```

- `{{#07}}` é a referência a outro ticket do backlog. O script troca pelo número real da issue no momento da criação, então as dependências sempre apontam para trás.
- **Mockups:** canvas [Integration AI Doctor — Mockups mobile first](https://claude.ai/artifact/KJnu4pFdbtiZgkuayGRpXz). Os números das telas ("Tela 6") são os mesmos usados no canvas.

## Milestones

| Milestone | Tema | Semanas |
|---|---|---|
| Sprint 1 — Fundação | Monorepo, Supabase, Auth, tenancy, API, contratos, app shell | 1–2 |
| Sprint 2 — Ingestão | Upload, ingestão, sanitização, framework de conectores, GCP | 3–4 |
| Sprint 3 — Correlação e incidentes | Correlação, regras, execuções, incidentes, dashboard | 5–6 |
| Sprint 4 — Inteligência artificial | Base de conhecimento, LLMProvider, diagnóstico, revisão | 7–8 |
| Sprint 5 — Segurança e avaliação | RLS, auditoria, retenção e LGPD, avaliação, cotas | 9–10 |
| Sprint 6 — Piloto | Relatórios, carga e backup, observabilidade, docs, piloto | 11–12 |
| v0.2 — Salesforce e SAP | Conectores e correlação entre sistemas | — |
| v0.3 — Alertas e ITSM | Notificações, webhooks, Jira, ServiceNow | — |
| v0.4 — IA privada | Inferência dedicada, modelo local, modelos menores | — |
| v1.0 — Operação empresarial | SSO, políticas, billing, HA, relatórios gerenciais, novos conectores | — |

## Labels

| Grupo | Labels |
|---|---|
| Tipo | `feature`, `chore`, `epic` |
| Camada | `frontend`, `backend`, `infra`, `database`, `ai` |
| Módulo | `M01-org`, `M02-connectors`, `M03-ingestion`, `M04-correlation`, `M05-diagnosis`, `M06-incidents`, `M07-knowledge`, `M08-audit` |
| Prioridade | `P0` (obrigatório na versão), `P1`, `P2` |
| Transversal | `security`, `lgpd`, `mobile` |

## Definition of Done (vale para todo ticket)

1. Testes escritos antes da implementação (`/tdd`) e passando no CI: unitários, integração e, quando houver tabela nova, **teste de isolamento entre tenants** em pgTAP ou pytest.
2. Migração em `supabase/migrations` com RLS ativado. O `supabase db lint` e os advisors de segurança passam.
3. Tipos regenerados (`supabase gen types`) e contratos atualizados em `packages/contracts`.
4. Telas: funcionam em 390 px sem rolagem horizontal, com alvos de toque ≥ 44 px, nos temas claro e escuro, e com textos em pt-BR.
5. Ações relevantes geram registro em `audit_logs` (a partir do ticket 28; antes disso, deixar o ponto de chamada pronto).
6. OpenAPI atualizado e endpoint documentado em `docs/api`.
7. Nenhum segredo ou dado pessoal em logs da aplicação.
8. Code review aprovado (`/code-review`).

## Vocabulário

Os termos seguem o [GLOSSARY.md](../../GLOSSARY.md). Decisões arquiteturais estão em [docs/adr](../adr).
