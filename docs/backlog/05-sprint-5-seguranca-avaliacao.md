milestone: Sprint 5 — Segurança e avaliação
description: Semanas 9–10. RLS completa com suíte de isolamento no CI, auditoria, retenção, exclusão e LGPD, dataset rotulado e avaliação, cotas e medição de uso.

<!-- issue: 27 -->
title: Auditoria completa de RLS e suíte de isolamento multi-tenant obrigatória no CI
labels: chore, database, security, P0
---
## Contexto
A meta do piloto é **0 vazamento entre tenants**. O PRD §10 diz que "testes de segurança multi-tenant são obrigatórios no pipeline de CI".

## Escopo
- Inventário automático: um teste pgTAP percorre `information_schema` e falha se alguma tabela de `public` estiver sem RLS, sem `tenant_id`, sem `unique (tenant_id, id)` ou com FK para tabela de tenant que não seja composta. Exceções explícitas: `tenants`, `global_*`, `rule_definitions`.
- Suíte de isolamento gerada por tabela: para cada tabela e operação (`select`/`insert`/`update`/`delete`) × papel × "outro tenant", verifica que não há acesso.
- Isolamento fora do banco:
  - API: para cada rota, uma fixture tenta acessar um recurso de B com o token de A e espera `404` (sem revelar a existência);
  - Storage: buckets `raw-logs`, `knowledge`, `reports`;
  - Realtime: assinar `diagnoses` de B com o token de A não entrega eventos;
  - workers: claims de serviço com escopo de tenant.
- Revisão das funções `security definer`: `search_path` fixo e `revoke execute from public`.
- Advisors do Supabase (security e performance) sem pendências críticas, verificados no CI pela branch de preview.
- Pentest interno guiado por checklist (OWASP ASVS L2, seções V1, V4 e V8), com relatório em `docs/security/`.

## Critérios de aceite
- O CI bloqueia o merge quando uma tabela nova não segue as convenções.
- Relatório da suíte com ≥ 300 asserções de isolamento, todas passando.

## Dependências
{{#24}}, {{#26}}

<!-- issue: 28 -->
title: Trilha de auditoria (audit_logs) e tela de auditoria
labels: feature, frontend, backend, database, security, M08-audit, mobile, P0
---
## Contexto
M08 (P0 para auditoria): histórico de alterações e rastreabilidade das decisões. A auditoria fica retida por 365 dias.

## Escopo
- `audit_logs (tenant_id, id bigserial, occurred_at, actor_type check in ('user','system','worker'), actor_id, action, resource_type, resource_id, before jsonb, after jsonb, ip inet, user_agent, request_id)`, **append-only**: sem `update`/`delete` para nenhum papel exceto o job de retenção. Particionada por mês.
- Emissão:
  - triggers genéricos em tabelas sensíveis: `memberships`, `invitations`, `connectors`, `integrations`, `retention_policies`, `tenants`;
  - chamadas explícitas na API para ações de negócio (`diagnosis.requested`, `diagnosis.feedback`, `raw_log.downloaded`, `report.exported`, `org.switched`);
  - `vault.secret_read` no `get_connector_secret`;
  - eventos de login e MFA a partir dos logs do Supabase Auth (hook ou consulta diária).
- `GET /api/v1/audit-logs` (Owner e Admin) com filtros e exportação CSV assíncrona.
- **Tela 18:** busca, chips de categoria e lista em formato de timeline (ator, ação, recurso e hora).

## UI — Tela 18
```text
┌──────────────────────────┐
│ ← Auditoria [Exportar CSV]│
│ [Filtrar usuário/ação]   │
│ (Todos)(Segurança)(Diag.)│
│ ● Júlia aceitou diag. v1 │
│ ● Sistema criou diag. v1 │
│ ● worker leu credencial  │
│ ● Rafael alterou papel … │
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** qualquer papel, **quando** tenta `update` ou `delete` em `audit_logs`, **então** falha.
- **Dado** a mudança de papel de um membro, **então** o registro tem `before` e `after`.
- Os registros não contêm segredos nem dados pessoais além do e-mail do ator.

## Dependências
{{#06}}, {{#14}}, {{#26}}

<!-- issue: 29 -->
title: Retenção, exclusão de dados e LGPD
labels: feature, frontend, backend, database, lgpd, M08-audit, mobile, P0
---
## Contexto
PRD §8: retenção padrão (Logs brutos 30 dias, Eventos 90, Incidentes e Diagnósticos 180, auditoria 365, Base de conhecimento até o cliente excluir), exclusão de dados e subprocessadores.

## Escopo
- `retention_policies (tenant_id, data_class, days)` com os padrões do PRD e limites mínimos e máximos por plano.
- Jobs `pg_cron` diários (03:00 BRT):
  - Logs brutos: apaga objetos do Storage e linhas de `raw_log_objects`;
  - Eventos: `DROP` de partições inteiras quando possível e `DELETE` por tenant quando a retenção for diferente da padrão;
  - Incidentes, Diagnósticos e auditoria.
  Cada execução gera um registro `retention.purge` em `audit_logs`.
- **Exclusão total da Organização:** só Owner com `aal2` e confirmação digitando o slug. Período de carência de 7 dias; depois, apaga dados do banco, do Storage e do Vault, revoga tokens e registra um comprovante.
- **Direitos do titular:** busca por HMAC de Referência de negócio para localizar e apagar Eventos de um titular, sob pedido do controlador.
- Toggle "Enviar evidências ao LLM": desligado equivale ao modo `rules_only` para todo o tenant.
- Página de subprocessadores (Supabase, Google Cloud, Anthropic, Voyage e Vertex, quando usado) com as regiões.
- Documentos em `docs/lgpd/`: modelo de DPA, papéis de controlador e operador, RIPD, transferência internacional e plano de resposta a incidentes.
- **Tela 16:** a seção de retenção e LGPD do menu "Mais".

## UI — Tela 16
```text
┌──────────────────────────┐
│ Mais             Acme ▾  │
│ Integrações / Conhec. /…›│
│ Retenção                 │
│ Logs brutos      30 dias │
│ Eventos          90 dias │
│ LGPD e IA                │
│ Enviar ao LLM      [on]  │
│ Subprocessadores       › │
│ [Solicitar exclusão total]│
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** uma retenção de Logs brutos de 30 dias, **quando** o job roda, **então** objetos com mais de 30 dias não existem no Storage, o que é verificado por listagem.
- **Dado** uma exclusão total concluída, **então** nenhuma tabela, bucket ou segredo do Vault contém o `tenant_id`, e um script de verificação comprova.
- **Dado** o toggle de LLM desligado, **então** nenhuma chamada ao provedor é feita para o tenant (verificado por métrica).

## Dependências
{{#28}}

<!-- issue: 30 -->
title: Dataset de incidentes rotulados e harness de avaliação (precisão, inconclusivos, custo)
labels: feature, backend, ai, M05-diagnosis, P0
---
## Contexto
Critérios do piloto: ≥ 100 incidentes históricos, precisão de categoria ≥ 85% e de Causa provável ≥ 75% (quando há evidência). A avaliação **inclui casos sem causa identificável**.

## Escopo
- `tests/evaluation/datasets/`: formato JSONL com Eventos (já sanitizados e anonimizados), gabarito (`category`, `probable_cause`, `responsible_system`, `expected_inconclusive`) e metadados de origem.
- Dataset v1 com ≥ 120 casos: sintéticos baseados nas regras INT-001 a INT-008, cerca de 40 reais anonimizados do cliente piloto com autorização, e ≥ 15 casos sem causa identificável.
- Ferramenta de rotulagem simples: CLI ou página interna para especialistas.
- Harness `make eval`: roda o `DiagnosisEngine` em `rules_only` e `hybrid` (por provedor e modelo) e calcula:
  - precisão por categoria (matriz de confusão);
  - precisão da Causa provável (avaliada por juiz LLM e checada por humano numa amostra de 20%);
  - taxa de inconclusivo correto e de "alucinação de evidência";
  - tokens, custo e latência p50 e p95.
- Relatório Markdown versionado em `tests/evaluation/reports/<data>.md`. Job semanal no CI com o provedor real.
- Gate de regressão: um PR que mexe em `diagnosis-engine` roda a avaliação em `rules_only` (rápida) e falha se a precisão cair mais de 2 p.p.

## Critérios de aceite
- Relatório v1 publicado com todas as métricas acima, por modo.
- O processo de calibração da Confiança fica documentado: enquanto não houver ≥ 500 casos, ela continua rotulada como heurística.

## Dependências
{{#24}}, {{#26}}

<!-- issue: 31 -->
title: Cotas e medição de uso por Organização
labels: feature, frontend, backend, database, M01-org, mobile, P0
---
## Contexto
M01 inclui "limites de utilização", e a API tem `GET /usage`. O PRD §12 manda impor limites por tenant para controlar o custo de IA. A cobrança em si fica para a v1.0 ({{#50}} no backlog futuro).

## Escopo
- `plan_limits (plan, resource, period, limit)` com os recursos `events_ingested`, `diagnoses_llm`, `storage_bytes`, `connectors_active` e `members`.
- `usage_records (tenant_id, resource, period_start, quantity, updated_at)`, com incremento atômico (`insert … on conflict do update`) a partir da ingestão, do diagnóstico, do Storage (job diário) e dos conectores. Os tokens de LLM ficam em `usage_llm (tenant_id, diagnosis_id, provider, model, input_tokens, output_tokens, cost_estimate)`.
- Imposição:
  - ingestão acima de 110% da Cota responde `429 quota_exceeded` com tolerância configurável;
  - diagnósticos com LLM acima da Cota passam a rodar em `rules_only` automaticamente, com aviso na tela;
  - conectores e membros acima do limite bloqueiam a criação.
- Avisos aos 80% e 100% (e-mail para Owner e Admin; push na v0.3).
- `GET /api/v1/usage`.
- **Tela 17:** barras por recurso, aviso de Cota e custo estimado de IA.

## UI — Tela 17
```text
┌──────────────────────────┐
│ ← Uso e cotas [Piloto]   │
│ Eventos 2,4mi/3mi ████▒  │
│ Diagnósticos 910/1000 ███│
│ ⚠ 91% — depois só regras │
│ Armazenamento 18/50 GB   │
│ Custo IA: 41,2mi tokens  │
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** 1.000 de 1.000 diagnósticos usados, **quando** um novo é solicitado, **então** roda em `rules_only` e a tela explica o motivo.
- Contadores consistentes sob concorrência: teste com 50 workers paralelos sem perder incrementos.

## Dependências
{{#12}}, {{#24}}
