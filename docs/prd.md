# PRD e Arquitetura Técnica — Integration AI Doctor

Versão 1.1 · 30/10/2026 · SaaS B2B · Mercado brasileiro
Baseado no PRD v1.0 (29/10/2026). **Mudança principal da v1.1:** o banco principal é o PostgreSQL do **Supabase**. Também passam a vir do Supabase o Auth, o Storage, o Realtime e o Vault (ver [ADR-0001](adr/0001-supabase-como-plataforma-de-dados.md)).
O vocabulário segue o [GLOSSARY.md](../GLOSSARY.md).

| | |
|---|---|
| Modelo comercial | SaaS B2B multi-tenant |
| Dados e identidade | **Supabase** (Postgres, Auth, Storage, Realtime, Vault), região São Paulo |
| Computação | Google Cloud (`southamerica-east1`): Cloud Run, Pub/Sub |
| Backend | Python 3.12 + FastAPI (API e workers) |
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui · PWA · **mobile first** |
| Diagnóstico | Regras + RAG (pgvector) + LLM (Claude por padrão, Vertex Gemini como alternativa) |

## 1. Resumo executivo

**Problema.** Para investigar um incidente de integração, as equipes de sustentação consultam logs de aplicação, middleware, respostas de APIs, mensagens SAP, dados do Salesforce e execuções em nuvem. A correlação é manual e depende de especialistas.

**Solução.** A plataforma:
1. recebe logs e eventos de vários sistemas;
2. correlaciona os Eventos de uma mesma Execução;
3. classifica a falha e levanta Hipóteses;
4. apresenta Evidências verificáveis, a Confiança e o Sistema responsável provável;
5. recomenda ações;
6. gera Relatórios técnicos em português e mantém o histórico.

**Critérios de sucesso do piloto**

| Indicador | Meta |
|---|---|
| Incidentes históricos avaliados | ≥ 100 |
| Precisão da categoria de falha | ≥ 85% |
| Precisão da Causa provável | ≥ 75% nos casos com evidência suficiente |
| Redução do tempo de investigação (MTTR) | ≥ 30% |
| Diagnósticos com evidência rastreável | 100% |
| Vazamento entre Organizações | 0 |
| Correções automáticas em produção | 0 no MVP |

A avaliação inclui casos sem causa identificável, nos quais o sistema precisa responder "Inconclusivo".

## 2. Arquitetura de referência

```text
┌───────────── Next.js (PWA, mobile first) ─────────────┐
│ Supabase Auth (sessão) · leituras simples via PostgREST│
│ Realtime (status do Diagnóstico) · escrita via API     │
└───────────────┬───────────────────────────┬────────────┘
                │ JWT Supabase              │ JWT
        ┌───────▼────────┐          ┌───────▼─────────┐
        │ FastAPI (Cloud │──outbox─▶│ Pub/Sub         │
        │ Run) /api/v1   │          └───────┬─────────┘
        └───────┬────────┘          ┌───────▼─────────────────────────┐
                │                   │ Workers Cloud Run: ingestion ·  │
                │                   │ correlation · diagnosis ·       │
                │                   │ connectors · retention          │
                │                   └───────┬─────────────────────────┘
        ┌───────▼───────────────────────────▼─────────┐     ┌──────────────┐
        │ Supabase: Postgres (RLS, pgvector, pg_cron, │     │ LLMProvider  │
        │ pg_partman) · Storage (raw-logs) · Vault ·  │     │ Claude/Vertex│
        │ Realtime · Auth (Custom Access Token Hook)  │     └──────────────┘
        └──────────────────────────────────────────────┘
```

| Decisão | Escolha | ADR |
|---|---|---|
| Forma | Monólito modular + workers | [0002](adr/0002-monolito-modular-e-workers.md) |
| Banco, Auth, Storage, Realtime | Supabase | [0001](adr/0001-supabase-como-plataforma-de-dados.md) |
| Hospedagem da computação | Cloud Run | 0001 |
| Fila | Pub/Sub + tabela outbox no Postgres | 0001 |
| Vetores | pgvector (Supabase) | — |
| Isolamento | RLS + FKs compostas + tenant vindo do JWT | [0004](adr/0004-isolamento-multi-tenant-rls-e-fks-compostas.md) |
| Status assíncrono | Supabase Realtime | [0005](adr/0005-realtime-para-status-de-diagnostico.md) |
| Credenciais de conectores | Supabase Vault | [0006](adr/0006-vault-para-credenciais-de-conectores.md) |
| IA | Núcleo determinístico + LLM assistivo | [0003](adr/0003-ia-assistiva-sobre-nucleo-deterministico.md), [0007](adr/0007-llm-provider-plugavel.md) |
| Observabilidade | OpenTelemetry → Cloud Trace/Monitoring | — |
| Infraestrutura | Terraform (GCP) + Supabase CLI (migrações) | — |

Residência de dados: Supabase `sa-east-1` e GCP `southamerica-east1`. Isso não garante, sozinho, residência integral. Backups, telemetria e o provedor de LLM são subprocessadores e precisam constar no contrato e no RIPD.

## 3. Módulos funcionais

| Módulo | Escopo | Prioridade |
|---|---|---|
| M01 Organizações | Multi-tenancy, Usuários, Convites, Papéis, Ambientes, Cotas | P0 |
| M02 Conectores | Cadastro, validação, autenticação, Sincronização incremental, estado, falhas | P0 |
| M03 Ingestão | Recepção, validação de contrato, Sanitização, deduplicação, persistência | P0 |
| M04 Correlação | Execuções por IDs técnicos, Referências de negócio, tempo, dependências | P0 |
| M05 Diagnóstico | Regras, RAG, Hipóteses, explicação por IA | P0 |
| M06 Dashboard e Incidentes | Indicadores, busca, filtros, Timeline, Evidências, comentários, status | P0 |
| M07 Base de conhecimento | Documentos, erros conhecidos, Incidentes resolvidos, Base global | P1 |
| M08 Relatórios e auditoria | Relatório técnico, Trilha de auditoria, feedback, rastreabilidade | P0 auditoria / P1 relatórios avançados |

## 4. Banco de dados (Supabase Postgres)

Convenções (ADR-0004):
- Toda tabela operacional tem `tenant_id uuid not null references tenants(id)`, `unique (tenant_id, id)` e FKs compostas.
- RLS ligado em todas as tabelas de `public`. As políticas usam `app.current_tenant_id()` e `app.current_role()`, lidos de `auth.jwt()`.
- Os Usuários são `auth.users`; dados de perfil ficam em `public.profiles`.
- O schema é versionado só em `supabase/migrations` (Supabase CLI).
- `events` é particionada por mês (pg_partman). Os Logs brutos ficam no Storage, nunca no banco.

| Tabela | Finalidade |
|---|---|
| `tenants` | Organizações (nome, slug, plano, região do LLM, status) |
| `profiles` | Perfil do Usuário (1:1 com `auth.users`) |
| `memberships` | Vínculo Usuário × Organização × Papel |
| `invitations` | Convites pendentes (token com hash, expiração) |
| `integrations` | Integrações monitoradas (origem, destino, Ambiente) |
| `connectors` | Conectores (provedor, config não secreta, `secret_id` no Vault, estado) |
| `connector_syncs` | Sincronizações e Checkpoints |
| `ingestion_tokens` | Tokens de máquina para `POST /ingestion/events` (hash) |
| `raw_log_objects` | Metadados dos Logs brutos no Storage (path, sha256, tamanho, expiração) |
| `imports` | Importações manuais (arquivo, status, contagens) |
| `executions` | Execuções correlacionadas |
| `events` | Eventos normalizados (particionada) |
| `incidents` | Incidentes (categoria, severidade, status, responsável) |
| `incident_comments` | Comentários |
| `rule_definitions` | Regras versionadas (código, versão, condição, ativa) |
| `rule_matches` | Regras que dispararam por Execução/Incidente |
| `diagnoses` | Diagnósticos versionados e imutáveis (status, Causa provável, Confiança, modelo, regras, chave de idempotência) |
| `diagnosis_hypotheses` | Hipóteses ordenadas |
| `diagnosis_evidence` | Evidências (tipo, `event_id` / `raw_log_object_id` / `chunk_id`, achado) |
| `diagnosis_recommendations` | Recomendações |
| `diagnosis_feedback` | Revisão humana (aceito, corrigido, rejeitado, categoria correta, nota) |
| `knowledge_documents` | Documentos da Base de conhecimento do tenant |
| `knowledge_chunks` | Fragmentos + `embedding vector(1024)` + `embedding_model` |
| `global_knowledge_documents` / `global_knowledge_chunks` | Base global (sem tenant_id, somente leitura) |
| `reports` | Relatórios gerados (path no Storage, formato) |
| `audit_logs` | Trilha de auditoria (append-only) |
| `usage_records` | Consumo por tenant, recurso e período |
| `plan_limits` | Cotas por plano |
| `retention_policies` | Retenção por tenant e classe de dado |
| `outbox_messages` | Mensagens a publicar no Pub/Sub (padrão outbox) |

O DDL inicial do PRD v1.0 (`tenants`, `integrations`, `executions`, `incidents`, `diagnoses`, `diagnosis_evidence`) continua válido. As migrações das issues completam o restante.

## 5. Conectores

Todos implementam a interface `Connector` (`packages/connectors/base`): `validate_config`, `test_connection`, `collect(checkpoint) -> (records, next_checkpoint)` e um `RateLimitPolicy`.

- **Google Cloud (P0, v0.1):** Cloud Logging (e Cloud Trace/BigQuery se necessário). Service Account com papel `roles/logging.viewer`, coleta incremental por janela de tempo, filtros por serviço, severidade e trace, e tratamento de paginação, cotas e retries.
- **Salesforce (P1, v0.2):** OAuth 2.0 (JWT bearer / web server flow), consultas SOQL parametrizadas e limitadas, correlação por Referência de negócio, respeito aos limites de API. O acesso a logs depende da edição e das licenças da org.
- **SAP (P1/P2, v0.2):** primeiro, respostas SAP presentes nos logs e arquivos exportados; depois, OData e SAP Integration Suite. Ambientes on-premises usam o agente local (outbound-only).

O Contrato de evento v1.0 é o mesmo do PRD original. O `tenant_id` nunca vem do payload: é derivado da identidade do Conector ou do token de ingestão. Referências de negócio sensíveis viram `hmac:` com chave derivada por tenant.

## 6. Motor de diagnóstico (6 etapas)

1. Validação e classificação → 2. Correlação → 3. Regras determinísticas (INT-001…INT-008, versionadas) → 4. Recuperação de conhecimento (tenant + Base global, nunca outros tenants) → 5. Interpretação por LLM (saída estruturada e validada) → 6. Verificação de referências, sinalização de incerteza e publicação.

O modo `rules_only` pula as etapas 4 e 5. O formato do resultado e as regras iniciais são os do PRD v1.0. A Confiança é heurística e aparece rotulada como tal na interface.

## 7. API REST `/api/v1`

Os endpoints do PRD v1.0 continuam: `integrations`, `connectors`, `connectors/{id}/test`, `ingestion/events`, `executions`, `executions/{id}`, `incidents`, `incidents/{id}`, `incidents/{id}/diagnoses`, `diagnoses/{id}`, `diagnoses/{id}/feedback`, `reports/{id}`, `usage`. A v1.1 acrescenta `me`, `orgs`, `orgs/{id}/switch`, `invitations`, `memberships`, `imports`, `knowledge/documents`, `audit-logs`, `retention-policies`, `ingestion-tokens`.

Escritas aceitam `Idempotency-Key`. O diagnóstico é assíncrono (`202` com `status: queued`) e o progresso chega pelo Realtime.

## 8. Segurança e LGPD

- **Isolamento:** RLS, FKs compostas e testes automatizados obrigatórios no CI (ADR-0004).
- **Identidade:** Supabase Auth (e-mail com magic link e senha, Google OAuth), MFA TOTP obrigatório para Owner e Admin, JWT de 1 h com refresh, SAML na v1.0.
- **Dados:** TLS, criptografia em repouso, Storage privado com URLs assinadas de até 5 min, Vault para credenciais.
- **Sanitização:** antes de persistir um Evento e antes de qualquer envio ao LLM, remove tokens, senhas, CPF/CNPJ, e-mails, telefones e cartões; impõe limites de tamanho e de formato.
- **Segurança da IA:** logs e documentos são tratados como dados não confiáveis (delimitados), sem ferramentas de escrita, com saída validada por schema e Evidências conferidas.
- **Governança:** papéis de controlador e operador definidos em contrato, retenção, exclusão, lista de subprocessadores (Supabase, Google, Anthropic/Voyage), resposta a incidentes, transferência internacional.

| Dado | Retenção padrão |
|---|---|
| Logs brutos | 30 dias |
| Eventos | 90 dias |
| Incidentes e Diagnósticos | 180 dias |
| Base de conhecimento | Até o cliente excluir |
| Auditoria | 365 dias |

## 9. Interface (mobile first)

O projeto parte de 390 px, sobe para tablet (≥ 768 px) e depois para desktop (≥ 1280 px, com sidebar).
- Navegação inferior: **Início · Incidentes · Execuções · Conectores · Mais**.
- Filtros abrem em bottom sheet; listas são cards com ações por toque (alvo ≥ 44 px).
- Temas claro e escuro; PWA instalável.

A interface é orientada à investigação: do alerta ao Evento original em no máximo 3 toques, sem depender do texto da IA.
Os mockups estão em [`docs/mockups/index.html`](mockups/index.html).

## 10. Repositório

```text
apps/web            Next.js (PWA)
apps/api            FastAPI
workers/{ingestion,correlation,diagnosis,connectors,retention}
packages/contracts  JSON Schema → tipos TS e modelos Pydantic
packages/connectors/{base,gcp,salesforce,sap}
packages/diagnosis-engine   (pipeline, regras, LLMProvider)
packages/knowledge          (chunking, embeddings, busca)
packages/security           (Sanitizer, HMAC)
supabase/{migrations,seed.sql,tests}   (pgTAP)
infrastructure/terraform
tests/{integration,security,evaluation,load}
docs/{adr,mockups,backlog}
```

## 11. Roadmap

| Milestone | Tema |
|---|---|
| Sprint 1 (sem. 1–2) | Fundação |
| Sprint 2 (sem. 3–4) | Ingestão |
| Sprint 3 (sem. 5–6) | Correlação e incidentes |
| Sprint 4 (sem. 7–8) | Inteligência artificial |
| Sprint 5 (sem. 9–10) | Segurança e avaliação |
| Sprint 6 (sem. 11–12) | Piloto |
| v0.2 | Conectores Salesforce e SAP |
| v0.3 | Alertas e ITSM |
| v0.4 | IA privada e modelos especializados |
| v1.0 | Operação empresarial (SSO, billing, HA) |

O backlog detalhado está em [`docs/backlog/`](backlog/).

## 12. Custos

Os custos se dividem em: Supabase (plano, compute add-on, armazenamento, egress, PITR), Cloud Run, Pub/Sub, LLM (tokens) e rede. Selecionar Evidências antes da inferência, usar cache e impor Cotas por tenant são obrigatórios.
**Premissa de capacidade:** 100 mil eventos/dia e 1.000 diagnósticos/mês, validada por teste de carga.

## 13. Checklist de liberação do MVP
- [ ] Isolamento entre tenants validado por testes automatizados
- [ ] Credenciais e dados sensíveis protegidos
- [ ] Conector GCP com sincronização incremental e recuperação de falhas
- [ ] Ingestão idempotente e sem perda silenciosa de eventos
- [ ] Diagnósticos com evidências verificáveis
- [ ] Casos inconclusivos tratados explicitamente
- [ ] Métricas de precisão e MTTR medidas no piloto
- [ ] Retenção, exclusão e auditoria implementadas
- [ ] Backup e restauração testados
- [ ] Documentação de instalação, operação e API disponível

## 14. Fora do escopo inicial
Plataforma iPaaS própria, reexecução automática em produção, treinamento de modelos próprios, dezenas de conectores, sistema completo de observabilidade.
