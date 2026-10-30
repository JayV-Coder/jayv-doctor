milestone: Sprint 6 — Piloto
description: Semanas 11–12. Relatório técnico, testes de carga e recuperação, observabilidade, documentação, implantação piloto, medição de MTTR e checklist de liberação.

<!-- issue: 32 -->
title: Relatório técnico exportável (PDF e Markdown)
labels: feature, frontend, backend, M08-audit, mobile, P1
---
## Contexto
O entregável 6 da v0.1 é "exporte um relatório técnico" em português para a equipe responsável (PRD §1 e `GET /reports/{id}`).

## Escopo
- `POST /api/v1/incidents/{id}/reports {format: pdf|md, include_timeline, include_event_excerpts}` → `202`. Um worker gera o arquivo, que vai para o Storage em `reports/{tenant_id}/…`.
- `GET /api/v1/reports/{id}` devolve metadados e uma URL assinada de 5 min.
- Template:
  - cabeçalho com Organização, Incidente, versão do Diagnóstico, versão das regras e modelo;
  - Resumo;
  - Causa provável **com o rótulo "confiança heurística"**;
  - Evidências com IDs rastreáveis;
  - Recomendações;
  - Revisão humana (veredito, revisor, comentário);
  - Timeline (opcional);
  - rodapé com data e hash do conteúdo.
- O PDF é gerado no servidor a partir de HTML (WeasyPrint), com fonte que suporta pt-BR.
- Link compartilhável opcional, que expira em 7 dias, é revogável e auditado.
- **Tela 19:** pré-visualização, formato, opções, "Baixar" e "Compartilhar link".

## UI — Tela 19
```text
┌──────────────────────────┐
│ ← Relatório              │
│ ┌ (pré-visualização) ───┐│
│ │ INC-0142 · Timeout…   ││
│ │ Resumo / Causa / Evid.││
│ └───────────────────────┘│
│ Formato [PDF ▾]          │
│ [x] Timeline completa    │
│ [Compartilhar] [Baixar PDF]
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** um Diagnóstico Inconclusivo, **então** o relatório diz "Evidências insuficientes" e lista o que coletar.
- O relatório não contém dados não sanitizados nem Referências de negócio em claro.
- Geração em < 10 s para Incidentes com até 100 Execuções.

## Dependências
{{#25}}, {{#26}}

<!-- issue: 33 -->
title: Testes de carga, backup e restauração (PITR)
labels: chore, infra, database, P0
---
## Contexto
O checklist de liberação inclui "Backup e restauração testados". A premissa de capacidade é de 100 mil eventos por dia e 1.000 diagnósticos por mês (PRD §12).

## Escopo
- k6 em `tests/load`:
  - ingestão sustentada de 3× a premissa (cerca de 3,5 eventos/s médios, com picos de 200/s por 10 min);
  - API de leitura (dashboard, listas): 50 usuários simultâneos;
  - 100 diagnósticos em 1 h.
- Metas: p95 da API de leitura < 500 ms, lag de ingestão p95 < 60 s, zero perda (contagem de ponta a ponta), sem erros 5xx acima de 0,1%.
- Dimensionamento do compute add-on do Supabase, do `pool_size` do Supavisor e de `max-instances` e concorrência no Cloud Run, com as conclusões em `docs/operations/capacity.md`.
- **Backup:** PITR habilitado em prod. Drill de restauração para um projeto novo em um ponto no tempo, com validação de integridade (contagens por tabela e amostra de hashes) e tempo medido (RTO e RPO documentados).
- Backup dos objetos do Storage: estratégia documentada (cópia diária para um bucket GCS em `southamerica-east1` com retenção alinhada).
- Runbook de recuperação em `docs/operations/runbooks/restore.md`.

## Critérios de aceite
- Relatório de carga anexado ao ticket, com todas as metas atingidas ou com tickets abertos para cada desvio.
- Drill de restauração executado com RTO e RPO registrados.

## Dependências
{{#12}}, {{#21}}, {{#24}}

<!-- issue: 34 -->
title: Observabilidade e alertas operacionais da plataforma
labels: chore, infra, backend, P0
---
## Contexto
O PRD usa OpenTelemetry. A plataforma precisa saber quando *ela própria* falha antes do cliente perceber.

## Escopo
- Traces de ponta a ponta: API → outbox → Pub/Sub → workers, com propagação de contexto nos atributos da mensagem.
- Métricas (Cloud Monitoring): lag da outbox, mensagens na DLQ, taxa de erro e latência da API, duração de Sincronizações, conectores em `failing`, tempo de diagnóstico por etapa, tokens e erros do LLM, conexões do Supavisor e uso de disco e CPU do Supabase (via Metrics API).
- Logs estruturados (JSON) sem PII, com `request_id` e `tenant_id`.
- Alertas:
  - DLQ > 0 por 5 min;
  - lag da outbox > 5 min;
  - API com 5xx > 1%;
  - workers sem processar por 10 min;
  - Supabase com CPU > 80% por 15 min;
  - erro do LLM > 10%.
  Destinos: e-mail e um canal de plantão.
- Dashboards operacionais versionados (Terraform).
- Status interno `/admin/health` para operadores da plataforma, separado dos tenants.

## Critérios de aceite
- Um evento injetado é rastreável da API até a gravação em `events` em um único trace.
- Cada alerta tem runbook vinculado em `docs/operations/runbooks/`.

## Dependências
{{#03}}, {{#12}}, {{#24}}

<!-- issue: 35 -->
title: Documentação, implantação piloto e medição de MTTR e usabilidade
labels: chore, P0
---
## Contexto
Os itens 7 a 10 do checklist (métricas no piloto e documentação disponível) e a Sprint 6 do roadmap: implantação piloto e medição de MTTR e usabilidade.

## Escopo
- Documentação:
  - `docs/api/` (OpenAPI publicado e guia de ingestão com exemplos `curl`, Python e Node);
  - `docs/operations/` (instalação dos ambientes, deploy, rotação de segredos, runbooks);
  - guia do usuário em pt-BR (primeiros passos, conector GCP, importação, leitura de um Diagnóstico).
- **Piloto:** Organização piloto criada, conector GCP configurado, importação dos 100+ incidentes históricos e treinamento da equipe (1 h).
- **Medição:**
  - baseline de MTTR (4 semanas anteriores, informado pelo cliente) contra o MTTR no piloto (dashboard de {{#21}});
  - tempo de revisão ({{#26}});
  - precisão da avaliação de {{#30}} sobre os incidentes do piloto;
  - SUS (questionário de usabilidade) com ≥ 5 usuários, incluindo uso no celular;
  - relatório final em `docs/pilot/report.md`.
- Coleta de feedback qualitativo transformado em issues da v0.2.

## Critérios de aceite
- Relatório do piloto com: precisão de categoria, precisão de causa, % de Diagnósticos com Evidência rastreável, redução de MTTR, vazamentos (0) e correções automáticas (0).

## Dependências
{{#21}}, {{#26}}, {{#30}}, {{#32}}

<!-- issue: 36 -->
title: Checklist de liberação do MVP (v0.1)
labels: epic, P0
---
## Contexto
Este é o ticket de acompanhamento da liberação, com o checklist do PRD §13. Cada item aponta para o ticket que o comprova.

## Checklist
- [ ] Isolamento entre tenants validado por testes automatizados ({{#27}})
- [ ] Credenciais e dados sensíveis protegidos ({{#13}}, {{#14}}, {{#27}})
- [ ] Conector GCP com sincronização incremental e recuperação de falhas ({{#15}})
- [ ] Ingestão idempotente e sem perda silenciosa de eventos ({{#12}}, {{#33}})
- [ ] Diagnósticos com evidências verificáveis ({{#24}})
- [ ] Casos inconclusivos tratados explicitamente ({{#24}}, {{#25}}, {{#30}})
- [ ] Métricas de precisão e MTTR medidas no piloto ({{#30}}, {{#35}})
- [ ] Retenção, exclusão e auditoria implementadas ({{#28}}, {{#29}})
- [ ] Backup e restauração testados ({{#33}})
- [ ] Documentação de instalação, operação e API disponível ({{#35}})

## Entregáveis da v0.1 (PRD §11)
1. Criar conta e configurar permissões ({{#04}}, {{#05}}, {{#06}})
2. Conectar projeto GCP ou importar logs ({{#11}}, {{#15}}, {{#16}})
3. Visualizar execuções e incidentes correlacionados ({{#19}}, {{#20}})
4. Solicitar diagnósticos com evidências ({{#24}}, {{#25}})
5. Revisar hipóteses e registrar feedback ({{#26}})
6. Exportar relatório técnico ({{#32}})
7. Consultar métricas de utilização e desempenho ({{#21}}, {{#31}})

## Dependências
Todos os tickets das Sprints 1 a 6.
