# API

A especificação completa (OpenAPI 3.1) é gerada da própria API (`make contracts`) e fica em [`packages/contracts/openapi.json`](../../packages/contracts/openapi.json). A versão navegável é publicada no GitHub Pages a cada merge na `main` (workflow `api-docs.yml`).

Todas as rotas ficam em `/api/v1`, com `Authorization: Bearer <JWT do Supabase>`. A Organização ativa vem do JWT, nunca do corpo. Os erros são `application/problem+json` com `code` estável. Rotas que criam algo aceitam `Idempotency-Key`.

| Tema | Documento |
|---|---|
| Ingestão por API (tokens, lotes, exemplos em curl, Python e Node) | [ingestion.md](ingestion.md) |
| Importação de arquivos | [imports.md](imports.md) |
| Integrações e Conectores | [integrations.md](integrations.md), [connectors.md](connectors.md) |
| Agentes locais (SAP on-premises) | [agents.md](agents.md) |
| Alertas e notificações (Regras, canais, push) | [alerts.md](alerts.md) |
| Webhooks de saída assinados | [webhooks.md](webhooks.md) |
| Mapas de identificadores (correlação entre sistemas, enriquecimento) | [correlation.md](correlation.md) |
| Execuções, Eventos e Logs brutos | [executions.md](executions.md) |
| Incidentes e Dashboard | [incidents.md](incidents.md), [dashboard.md](dashboard.md) |
| Diagnósticos e revisão | [diagnoses.md](diagnoses.md) |
| Relatório técnico e link compartilhável | [reports.md](reports.md) |
| Base de conhecimento | [knowledge.md](knowledge.md) |
| Organizações, membros e sessão | [orgs.md](orgs.md), [members.md](members.md), [me.md](me.md) |
| Trilha de auditoria, privacidade e Cotas | [audit.md](audit.md), [privacy.md](privacy.md), [usage.md](usage.md) |
| Plataforma | [platform.md](platform.md) |
