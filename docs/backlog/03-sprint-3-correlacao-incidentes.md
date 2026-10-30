milestone: Sprint 3 — Correlação e incidentes
description: Semanas 5–6. Motor de correlação, regras determinísticas INT-001…008, explorador e timeline de execuções, incidentes e dashboard executivo.

<!-- issue: 17 -->
title: Motor de correlação de Execuções
labels: feature, backend, M04-correlation, P0
---
## Contexto
M04 do PRD: associar Eventos por identificadores técnicos, Referências de negócio, timestamps e dependências, e reconstruir a Execução.

## Escopo
- `packages/correlation` com a interface `Correlator.correlate(tenant_id, event_ids) -> CorrelationResult`. As estratégias são ordenadas por força e o resultado registra qual delas associou cada Evento (`correlated_by`):
  1. `execution_id` igual dentro da Integração;
  2. `trace_id` igual;
  3. Referência de negócio igual e `operation` compatível, numa janela de 15 min (configurável);
  4. proximidade temporal ≤ 2 s com o mesmo `source.resource` e `attempt` sequencial (estratégia fraca, marcada como `low_confidence`).
- Tabela `executions` (DDL do PRD) com `status check in ('success','failed','pending_confirmation','unknown')`, `duration_ms`, `event_count`, `first_event_at`, `last_event_at` e `correlation_keys jsonb`. A coluna `events.execution_ref uuid` liga cada Evento à Execução, e `events.correlated_by text` guarda a estratégia.
- Worker `correlation`: consome `correlation.requested` (lotes por tenant e Integração), faz upsert de Execuções e recalcula o status. Uma Execução fica "aberta" por 5 min após o último Evento; depois é fechada e publica `rules.evaluate`.
- Fusão: se dois grupos se revelam a mesma Execução (por exemplo, o trace chega depois), funde em uma só, mantendo o histórico em `execution_merges`.
- Determinístico: a mesma entrada sempre produz a mesma saída, independentemente da ordem de chegada.

## Critérios de aceite
- **Dado** os 6 Eventos do exemplo do mockup (Tela 8), chegando fora de ordem, **então** formam uma Execução com 6 Eventos, status `failed` e `duration_ms` correto.
- **Dado** um Evento sem `execution_id` nem `trace_id`, mas com a mesma Referência de negócio dentro da janela, **então** é associado com `correlated_by = 'business_reference'`.
- **Dado** Eventos de tenants diferentes com o mesmo `trace_id`, **então** nunca formam a mesma Execução.

## Testes
- Testes property-based: permutações de ordem produzem o mesmo resultado.
- Dataset sintético com 1 mil Execuções e gabarito, com precisão de agrupamento ≥ 98%.

## Dependências
{{#12}}

<!-- issue: 18 -->
title: Regras determinísticas versionadas (INT-001…INT-008) e abertura de Incidentes
labels: feature, backend, database, M05-diagnosis, M06-incidents, P0
---
## Contexto
A etapa 3 do motor ([ADR-0003]({{repo}}/docs/adr/0003-ia-assistiva-sobre-nucleo-deterministico.md)) é a classificação inicial por regras na Sprint 3. As regras classificam sintomas e **não atribuem responsabilidade definitiva**.

## Escopo
- `packages/diagnosis-engine/rules`: regras como código Python puro e testável (`Rule.evaluate(execution, events) -> RuleMatch | None`), com metadados `code`, `version`, `category`, `severity_hint`, `description_pt` e `evidence_selector`.
- Pacote versionado `rules@2026.10.1`. Cada versão é registrada em `rule_definitions (code, version, category, description, active, created_at)`, uma tabela global somente leitura.
- Regras iniciais (PRD §6):
  | Código | Condição | Classificação |
  |---|---|---|
  | INT-001 | HTTP 401/403 | AUTH |
  | INT-002 | HTTP 429 | RATE_LIMIT |
  | INT-003 | HTTP 504 ou timeout | TIMEOUT (resultado remoto indeterminado) |
  | INT-004 | Erro de validação de payload | VALIDATION |
  | INT-005 | Mensagem de rejeição SAP (tipo E/A em BAPIRET2, `V1`, `VL` …) | BUSINESS_REJECTION |
  | INT-006 | Identificador já existente / duplicate | DUPLICATE |
  | INT-007 | Enviado sem confirmação em X min | PENDING_CONFIRMATION |
  | INT-008 | Divergência origem × destino (contagens e status) | DIVERGENCE |
- `rule_matches (tenant_id, id, execution_id, rule_code, rule_version, matched_event_ids uuid[], details jsonb)`.
- **Abertura de Incidentes:** Execuções com match são agrupadas por (Integração, categoria, janela de 30 min) num mesmo Incidente aberto. Isso evita um Incidente por Execução.
  - Tabela `incidents` (DDL do PRD) com `title`, `integration_id`, `first_seen_at`, `last_seen_at`, `execution_count`, `assignee_id`, `resolved_at` e `resolution_note`.
  - Tabela `incident_executions (tenant_id, incident_id, execution_id)`.
- Severidade inicial: regra mais Ambiente (prd sobe um nível) mais volume (≥ 20 Execuções sobe para crítico).
- Publica `incident.opened` e `incident.updated` (usados depois por {{#24}} e pelos alertas da v0.3).

## Critérios de aceite
- **Dado** 37 Execuções com HTTP 504 em 18 min na mesma Integração prd, **então** existe **um** Incidente crítico `TIMEOUT` com `execution_count = 37`.
- **Dado** uma nova versão de regra, **então** os matches antigos continuam apontando para a versão antiga (rastreabilidade).
- Cada regra tem ao menos 3 testes positivos e 3 negativos.

## Testes
- Testes unitários por regra, mais um teste de ponta a ponta (Eventos → Execução → Incidente) com fixtures.

## Dependências
{{#17}}

<!-- issue: 19 -->
title: Explorador de Execuções, Timeline e Evento original
labels: feature, frontend, backend, M04-correlation, M06-incidents, mobile, P0
---
## Contexto
O PRD §9 descreve o "Explorador de execuções: pesquisa por trace ID, integração, ambiente, status e intervalo de datas", com Timeline correlacionada. O princípio é poder chegar ao Evento original **sem depender do texto da IA**.

## Escopo
- API:
  - `GET /api/v1/executions?integration_id&environment&status&from&to&q` com paginação por cursor. `q` aceita `trace_id`, `execution_id` ou o termo de Referência de negócio, que passa por HMAC no servidor;
  - `GET /api/v1/executions/{id}`: metadados mais Eventos ordenados, `correlated_by`, regras que dispararam e Incidente vinculado;
  - `GET /api/v1/events/{id}` e `GET /api/v1/raw-logs/{id}/download`, que devolve uma URL assinada de 5 min e registra auditoria.
- **Tela 7:** busca no topo, chips de filtros rápidos, bottom sheet de filtros completos, lista com status em cor **e** texto, e chip do Incidente.
- **Tela 8:** cabeçalho com Integração, trace, Referência (HMAC) e duração; Timeline vertical com severidade e a estratégia de correlação; o Evento com match de regra aparece destacado e tem chip da regra.
- **Tela 9:** JSON normalizado com realce de sintaxe, alternância para Log bruto, resumo da Sanitização, origem (Conector e Sincronização) e dias restantes de retenção.
- Desempenho: listar 50 Execuções em < 300 ms p95 com 10 milhões de Eventos (índices de {{#12}}).

## UI — Telas 7, 8 e 9
```text
Timeline
┌──────────────────────────┐
│ ← exec-123     [INC-0142]│
│ Integração  SF→SAP · prd │
│ Trace       trace-abc    │
│ ● 14:02:01 SF Outbound   │
│ ● 14:02:01 Transformação │
│ ● 14:02:01 BAPI create   │
│ ◉ 14:02:31 HTTP 504 [INT-003]
│ ● Retry agendado         │
│ ○ Sem confirmação do SAP │
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** um número de pedido digitado na busca, **então** a Execução é encontrada sem que o número apareça em nenhum log da API.
- **Dado** um Viewer, **quando** pede o download do Log bruto, **então** `403`. O download fica restrito a Analyst ou superior e é auditado.
- Do Incidente ao Evento original em no máximo 3 toques: Incidente → Evidência → Evento.

## Testes
- Playwright mobile: busca por trace, abrir Timeline e abrir Evento.
- Teste de desempenho com seed de 10 milhões de Eventos (job noturno).

## Dependências
{{#09}}, {{#17}}, {{#18}}

<!-- issue: 20 -->
title: Incidentes (lista, detalhe, status, responsável, comentários)
labels: feature, frontend, backend, database, M06-incidents, mobile, P0
---
## Contexto
M06 do PRD: pesquisa, filtros, Timeline, Evidências, classificação, comentários e status.

## Escopo
- Status: `open → investigating → resolved | dismissed`, com reabertura permitida e transições validadas no banco (trigger).
- `incident_comments (tenant_id, id, incident_id, author_id, body_md, created_at, edited_at)` com menções `@` a membros.
- API: `GET /api/v1/incidents` (filtros: status, severidade, categoria, Integração, Ambiente, responsável, período, `q`), `GET /api/v1/incidents/{id}`, `PATCH` (status, severidade, responsável, nota de resolução), e `POST/GET /api/v1/incidents/{id}/comments`.
- **Tela 5:** busca, chips de status com contagem e cards com severidade, ID, título, categoria/regra, estado do Diagnóstico (placeholder até {{#25}}) e Integração.
- **Detalhe (base da Tela 6):** cabeçalho com severidade, status editável e Integração; resumo (Execuções afetadas, primeira e última ocorrência); Execuções vinculadas; regras disparadas como Evidências determinísticas; comentários. A seção de Diagnóstico entra em {{#25}}.
- Resolver exige nota de resolução, que alimenta a Base de conhecimento em {{#26}}.
- Atualização em tempo real da lista (Realtime em `incidents`).

## UI — Tela 5
```text
┌──────────────────────────┐
│ Incidentes      Acme ▾   │
│ [Buscar ID/trace/pedido][≡]
│ (Abertos 12)(Em análise)…│
│ ┌ [Crítico] INC-0142 18m┐│
│ │ Timeout criação SAP   ││
│ │ [UPSTREAM_TIMEOUT][v1]││
│ └───────────────────────┘│
│ Início [Inc] Exec Con  + │
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** um Incidente `resolved`, **quando** chega uma nova Execução com a mesma assinatura em até 24 h, **então** ele é reaberto (não se cria um novo) e o histórico registra a reabertura.
- **Dado** um Viewer, **então** não vê os controles de status nem o campo de comentário.
- A lista carrega os primeiros 20 itens em < 1 s em 4G simulado.

## Testes
- pgTAP: transições de status inválidas falham.
- E2E: mudar status, comentar e resolver com nota.

## Dependências
{{#18}}, {{#19}}

<!-- issue: 21 -->
title: Dashboard executivo
labels: feature, frontend, backend, database, M06-incidents, mobile, P0
---
## Contexto
O PRD §9 lista total de execuções, falhas por categoria, taxa de erro, incidentes abertos, tendência temporal e tempo médio de resolução (MTTR, a métrica de sucesso do piloto).

## Escopo
- Agregados:
  - tabela `execution_stats_hourly (tenant_id, integration_id, environment, hour, total, failed, by_category jsonb)`, mantida pelo worker de correlação (upsert incremental) e reconciliada por um job `pg_cron` a cada hora;
  - MTTR = média de `resolved_at - first_seen_at` dos Incidentes resolvidos no período, com o baseline do piloto configurável em `tenants.mttr_baseline_minutes`.
- `GET /api/v1/dashboard?period=24h|7d|30d&environment&integration_id`.
- **Tela 4 (mobile):** filtros de período e Ambiente; card destacado do Incidente crítico mais recente; 4 KPIs (Execuções, Taxa de erro, Incidentes abertos, MTTR) com variação; gráfico de falhas por hora (barras); falhas por categoria (barras horizontais).
- **Desktop:** grade de 4 KPIs, gráfico mais categorias lado a lado e tabela de incidentes recentes (mockup "Dashboard desktop").
- Gráficos acessíveis: `aria-label` com o resumo e tabela equivalente para leitores de tela.

## UI — Tela 4
```text
┌──────────────────────────┐
│ Início   Acme Consultoria▾│
│ (24h)(7d)(30d)(Produção▾)│
│ ┌ Crítico · INC-0142 ───┐│
│ │ Timeout pedidos SAP   ││
│ └───────────────────────┘│
│ [Execuções 18.402][Erro 3,4%]
│ [Abertos 12][MTTR 2h10 −34%]
│ ▁▂▁▃▂▄▃█▅▃▂▂ falhas/hora │
│ Timeout ██████ 41        │
│ Início Inc Exec Con  +   │
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** o seed de referência, **então** os KPIs batem com as consultas SQL de controle, com no máximo 1 h de atraso.
- O dashboard carrega em < 1,5 s (p95) com 30 dias de dados de um tenant de 100 mil eventos por dia.

## Testes
- Testes do cálculo de MTTR e da taxa de erro com casos de borda: período vazio, Incidente reaberto.

## Dependências
{{#20}}
