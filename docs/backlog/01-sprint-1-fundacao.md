milestone: Sprint 1 — Fundação
description: Semanas 1–2. Monorepo, CI/CD, Supabase, Terraform, Auth, tenancy, RBAC, API base, contrato de eventos, app shell e Integrações.

<!-- issue: 01 -->
title: Monorepo, ferramentas e CI base
labels: chore, infra, P0
---
## Contexto
O repositório está vazio. Todos os outros tickets dependem de uma estrutura padronizada (PRD §10, [ADR-0002]({{repo}}/docs/adr/0002-monolito-modular-e-workers.md)).

## Escopo
- Estrutura de pastas do PRD §10: `apps/web`, `apps/api`, `workers/*`, `packages/*`, `supabase/`, `infrastructure/terraform`, `tests/*`, `docs/*`.
- **TS:** pnpm workspaces + Turborepo, TypeScript strict, ESLint, Prettier, Vitest.
- **Python:** uv workspace (Python 3.12), Ruff (lint e format), mypy strict, pytest. Um `pyproject.toml` por pacote ou app.
- `Makefile` ou `justfile` com `dev`, `test`, `lint`, `typecheck`, `db:reset`, `db:types`.
- GitHub Actions `ci.yml`: lint, typecheck e testes de TS e Python em paralelo, com cache do pnpm e do uv. Jobs separados para `supabase db lint` e pgTAP (preparados para {{#02}}).
- `CODEOWNERS`, template de PR e de issue, `.editorconfig`, `.gitignore`, Renovate.
- Pre-commit: ruff, prettier e detecção de segredos (gitleaks).

## Fora de escopo
Deploy (fica em {{#03}}) e código de produto.

## Critérios de aceite
- **Dado** um clone limpo, **quando** executo `make dev-setup && make test`, **então** tudo passa sem configuração manual além do `.env.example`.
- **Dado** um PR com erro de lint em TS ou Python, **quando** o CI roda, **então** o check falha e indica o arquivo.
- **Dado** um segredo commitado por engano, **quando** o pre-commit ou o CI rodam, **então** o gitleaks bloqueia.

## Testes
- Smoke test em cada pacote (um teste trivial) para validar a orquestração do Turborepo e do pytest.

## Dependências
Nenhuma.

<!-- issue: 02 -->
title: Projeto Supabase, stack local e convenções de migração multi-tenant
labels: chore, database, infra, security, P0
---
## Contexto
O Supabase é a plataforma de dados ([ADR-0001]({{repo}}/docs/adr/0001-supabase-como-plataforma-de-dados.md)). Antes de qualquer tabela de domínio, precisamos dos padrões de isolamento ([ADR-0004]({{repo}}/docs/adr/0004-isolamento-multi-tenant-rls-e-fks-compostas.md)).

## Escopo
- Projetos Supabase **dev**, **staging** e **prod** na região `sa-east-1` (São Paulo). Branching do Supabase habilitado para PRs.
- `supabase init`, com `config.toml` versionado. `supabase start` sobe Postgres, Auth, Storage, Realtime e Studio localmente.
- Migração `0000_extensions`: `pgcrypto`, `vector`, `pg_cron`, `pg_partman`, `pgtap` (apenas em teste).
- Migração `0001_app_schema`:
  - schema `app` com helpers `app.current_tenant_id()` (lê `auth.jwt() ->> 'tenant_id'`, `stable`), `app.current_role()` e `app.has_role(variadic text[])`;
  - função `app.set_updated_at()` com trigger padrão;
  - tabela `tenants (id uuid pk, name, slug unique, plan text default 'pilot', llm_provider text default 'anthropic', status, created_at)` com RLS.
- Documento `supabase/CONVENTIONS.md` com o checklist de tabela nova: `tenant_id not null`, `unique (tenant_id, id)`, FKs compostas, RLS ligado, policies `select/insert/update/delete` por papel, índices iniciados por `tenant_id`, teste pgTAP de isolamento.
- `supabase/tests/00_isolation_helpers.sql`: helpers pgTAP para "autenticar como usuário X no tenant Y".
- CI: `supabase db reset`, `supabase test db`, `supabase db lint` e os advisors de segurança (`get_advisors`) contra a branch de preview.

## Critérios de aceite
- **Dado** um usuário com claim `tenant_id = A`, **quando** ele faz `select` em `tenants`, **então** vê apenas a linha A.
- **Dado** uma tabela nova sem RLS, **quando** o CI roda, **então** o lint ou advisor falha.
- **Dado** o desenvolvedor local, **quando** roda `make db:reset`, **então** o banco é recriado com migrações e seed em menos de 60 s.

## Segurança / LGPD
- A `service_role` key nunca vai para o frontend nem para logs. As chaves ficam no Secret Manager ({{#03}}).
- PITR habilitado no projeto prod (exigência do checklist de liberação).

## Testes
- pgTAP: `app.current_tenant_id()` retorna null sem JWT e o UUID correto com JWT; RLS em `tenants`.

## Dependências
{{#01}}

<!-- issue: 03 -->
title: Infraestrutura GCP com Terraform (Cloud Run, Pub/Sub, Artifact Registry, WIF)
labels: chore, infra, P0
---
## Contexto
A computação roda no GCP `southamerica-east1` ([ADR-0001]({{repo}}/docs/adr/0001-supabase-como-plataforma-de-dados.md)).

## Escopo
- `infrastructure/terraform` com módulos `project`, `network`, `run-service`, `pubsub-topic`, `secrets`, `observability` e ambientes `dev`, `staging`, `prod` (state em GCS com lock).
- Artifact Registry para as imagens da API e dos workers.
- Cloud Run: `api` (público via HTTPS LB e Cloud Armor com rate limit por IP) e `worker-*` (somente push autenticado do Pub/Sub).
- Tópicos Pub/Sub e assinaturas push com DLQ: `ingestion.raw`, `ingestion.normalized`, `correlation.requested`, `diagnosis.requested`, `connector.sync`. Política de retry exponencial; DLQ após 5 tentativas.
- Secret Manager para segredos **da plataforma**: URL do pooler do Supabase, JWT secret ou JWKS, chaves de LLM, chave HMAC mestre.
- Workload Identity Federation para o GitHub Actions (sem chave JSON). Workflow `deploy.yml`: build, push e deploy por ambiente, com aprovação manual para prod.
- Service accounts com o mínimo de privilégio por serviço.

## Critérios de aceite
- **Dado** um merge na `main`, **quando** o workflow roda, **então** a API e os workers são publicados em staging com a imagem do commit.
- **Dado** uma mensagem que falha 5 vezes, **quando** o Pub/Sub desiste, **então** ela fica na DLQ com alerta (o alerta vem em {{#34}}).
- `terraform plan` sem diff após o apply.

## Segurança
- Nenhuma chave de service account exportada. Cloud Run com `--no-allow-unauthenticated` nos workers.

## Dependências
{{#01}}

<!-- issue: 04 -->
title: Autenticação com Supabase Auth (magic link, senha, Google) e MFA para Owner/Admin
labels: feature, frontend, backend, security, M01-org, mobile, P0
---
## Contexto
O PRD pede OIDC, MFA para administradores e sessões curtas. O Supabase Auth atende a esses três pontos.

## História de usuário
Como **analista de sustentação**, quero entrar pelo celular com o e-mail corporativo ou com o Google, para investigar um incidente de onde eu estiver.

## Escopo
- Provedores: e-mail (magic link e senha) e Google OAuth. JWT de 1 h com refresh token rotativo.
- Tabela `public.profiles (id uuid pk references auth.users, full_name, avatar_url, locale default 'pt-BR', created_at)`, criada por trigger em `auth.users`.
- MFA TOTP (Supabase Auth MFA): cadastro, verificação e códigos de recuperação. **Obrigatório** para Owner e Admin: a API e as policies exigem `aal2` para ações administrativas.
- Telas: login, verificação de MFA, cadastro de fator, "esqueci minha senha" e logout.
- Templates de e-mail em pt-BR.
- `GET /api/v1/me`: perfil, organizações e papel na Organização ativa.

## UI — Tela 1 (mockup no canvas)
```text
┌──────────────────────────┐
│ [logo] Integration AI Dr │
│ E-mail corporativo [___] │
│ [ Enviar link de acesso ]│
│ ─────── ou ───────       │
│ [ Continuar com Google ] │
│ [ Entrar com senha ]     │
│ ┌ MFA (Admin) ─────────┐ │
│ │ [4][8][1][ ][ ][ ]   │ │
│ │ [ Verificar ]        │ │
│ └──────────────────────┘ │
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** um Admin sem MFA cadastrado, **quando** ele faz login, **então** é obrigado a cadastrar um fator antes de acessar qualquer tela.
- **Dado** uma sessão `aal1` de um Admin, **quando** ele chama uma ação administrativa, **então** recebe `403 mfa_required`.
- **Dado** um token expirado, **quando** o app faz uma requisição, **então** o refresh acontece de forma transparente.
- Login completo em 390 px com teclado virtual aberto e sem rolagem horizontal.

## Segurança / LGPD
- Rate limit de tentativas (configuração do Auth) e e-mails com links de uso único.
- Política de privacidade com link na tela.

## Testes
- E2E com Playwright: login por magic link usando o Inbucket local e fluxo de MFA.
- API: dependência `require_aal2` em pytest.

## Dependências
{{#02}}

<!-- issue: 05 -->
title: Organizações, vínculos, Organização ativa no JWT e seletor
labels: feature, frontend, backend, database, security, M01-org, mobile, P0
---
## Contexto
Um Usuário pode pertencer a várias Organizações, o que é comum em consultorias. O `tenant_id` ativo vai no JWT por meio do *Custom Access Token Hook* e é a base de todo o RLS ([ADR-0004]({{repo}}/docs/adr/0004-isolamento-multi-tenant-rls-e-fks-compostas.md)).

## História de usuário
Como **consultora**, quero alternar entre as Organizações dos meus clientes sem misturar dados.

## Escopo
- Tabela `memberships (tenant_id, user_id, role check in ('owner','admin','analyst','viewer'), created_at, unique (tenant_id, user_id))`.
- Tabela `user_active_tenant (user_id pk, tenant_id)`.
- Função `custom_access_token_hook(event jsonb)`: injeta `tenant_id` e `tenant_role` a partir do tenant ativo, mas só se houver Vínculo. Sem Vínculo, as claims ficam nulas.
- `POST /api/v1/orgs`: cria a Organização e o Vínculo Owner numa só transação.
- `POST /api/v1/orgs/{id}/switch`: valida o Vínculo, atualiza o tenant ativo e o cliente força `refreshSession()`.
- Onboarding (Tela 2): nome, slug, segmento, escolha do provedor de IA (Claude ou Vertex) e aceite do DPA (gravado em `tenants.dpa_accepted_at`).
- Seletor (Tela 3): bottom sheet com busca e criação de nova Organização.

## UI — Telas 2 e 3
```text
Seletor (bottom sheet)
┌──────────────────────────┐
│ Trocar de organização    │
│ [Buscar organização    ] │
│ (AC) Acme Consultoria  ✓ │
│ (VB) Varejo Brasil       │
│ (IM) Indústria Meridional│
│ [+ Criar nova organização]│
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** um usuário com Vínculo em A e B e ativo em A, **quando** troca para B, **então** o novo JWT tem `tenant_id = B` e nenhuma tela mostra dados de A após o refresh.
- **Dado** um usuário sem Vínculo em C, **quando** tenta `switch` para C, **então** recebe `403` e as claims não mudam.
- **Dado** um Vínculo removido, **quando** o token é renovado, **então** as claims de tenant somem.

## Testes
- pgTAP: o hook retorna claims corretas e nulas. Isolamento de `memberships`.
- E2E: criar Organização, trocar e verificar que o dashboard muda.

## Dependências
{{#04}}

<!-- issue: 06 -->
title: Convites e RBAC (Owner, Admin, Analyst, Viewer)
labels: feature, frontend, backend, database, security, M01-org, mobile, P0
---
## Contexto
O PRD §8 define quatro papéis. Este ticket estabelece a matriz de permissões usada por todos os outros.

## Matriz de permissões
| Ação | Owner | Admin | Analyst | Viewer |
|---|---|---|---|---|
| Ver dashboards, incidentes, execuções | ✓ | ✓ | ✓ | ✓ |
| Comentar, mudar status, solicitar diagnóstico, revisar | ✓ | ✓ | ✓ | — |
| Importar logs | ✓ | ✓ | ✓ | — |
| Gerenciar integrações e conectores | ✓ | ✓ | — | — |
| Gerenciar membros e convites | ✓ | ✓ (exceto Owner) | — | — |
| Retenção, exclusão, provedor de IA, cobrança | ✓ | — | — | — |

## Escopo
- `invitations (tenant_id, email citext, role, token_hash, invited_by, expires_at default now()+7d, accepted_at)`.
- `POST /api/v1/invitations`, `POST /api/v1/invitations/{token}/accept`, `DELETE /api/v1/invitations/{id}`, `PATCH /api/v1/memberships/{id}` (papel) e `DELETE /api/v1/memberships/{id}`.
- E-mail de convite em pt-BR. Ao aceitar, cria o Vínculo e define a Organização ativa.
- Regras: sempre deve existir ao menos um Owner, e um Admin não promove ninguém a Owner.
- Dependência FastAPI `require_role(...)` e policies RLS com `app.has_role(...)`.
- Tela 15: lista de membros, convites pendentes (reenviar, revogar) e formulário de convite.

## UI — Tela 15
```text
┌──────────────────────────┐
│ ← Membros     [Convidar] │
│ (AS) Ana Souza    Owner  │
│ (RM) Rafael       Admin  │
│ (JL) Júlia       Analyst │
│ Convites pendentes       │
│ carla@… Analyst [Reenviar]│
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** um Viewer, **quando** tenta `POST /incidents/{id}/diagnoses`, **então** recebe `403`. A mesma regra vale via PostgREST pelo RLS.
- **Dado** o único Owner, **quando** tenta se rebaixar, **então** recebe `409 last_owner`.
- **Dado** um convite expirado, **quando** é aceito, **então** recebe `410`.
- Tokens de convite guardados apenas como hash (sha256).

## Testes
- Testes parametrizados da matriz inteira (papel × endpoint) em pytest.
- pgTAP com a mesma matriz para as policies.

## Dependências
{{#05}}

<!-- issue: 07 -->
title: Esqueleto da API FastAPI (JWT Supabase, contexto de tenant, RBAC, rate limit, OpenAPI, OTel)
labels: chore, backend, security, P0
---
## Contexto
A API é a porta de toda escrita ([ADR-0002]({{repo}}/docs/adr/0002-monolito-modular-e-workers.md)). O RLS precisa valer dentro dela ([ADR-0004]({{repo}}/docs/adr/0004-isolamento-multi-tenant-rls-e-fks-compostas.md)).

## Escopo
- `apps/api` com FastAPI, Pydantic v2 e SQLAlchemy 2 Core (async, `asyncpg`) via **Supavisor modo transação**. Sem ORM pesado.
- Módulos (monólito modular): `orgs`, `integrations`, `connectors`, `ingestion`, `executions`, `incidents`, `diagnosis`, `knowledge`, `reports`, `audit`, `usage`. Cada um com `router.py`, `service.py` e `repo.py`, e imports cruzados proibidos (regra do import-linter).
- **Auth:** valida o JWT do Supabase (JWKS com cache) e extrai `sub`, `tenant_id`, `tenant_role` e `aal`.
- **Tenant context (seam central):** `async with tenant_tx(claims) as conn` executa `SET LOCAL role authenticated` e `select set_config('request.jwt.claims', :claims, true)`. Todo acesso a dados passa por ele.
- `require_role`, `require_aal2`, middleware `Idempotency-Key` (tabela `idempotency_keys (tenant_id, key, request_hash, response, created_at)`, TTL de 24 h).
- Rate limit por tenant e usuário (token bucket no Postgres ou em memória por instância, com limite global no Cloud Armor).
- Erros RFC 7807 (`application/problem+json`) em pt-BR.
- OpenAPI em `/api/v1/openapi.json` e geração do cliente TS em `packages/contracts` (`openapi-typescript`).
- OpenTelemetry (traces e métricas) com `tenant_id` como atributo (nunca o e-mail), exportado para o Cloud Trace.
- Health checks `/healthz` e `/readyz` (o readyz testa o banco).

## Critérios de aceite
- **Dado** um JWT de tenant A, **quando** um endpoint consulta uma tabela com RLS sem filtrar por tenant, **então** só retorna dados de A, porque o RLS age dentro da API.
- **Dado** a mesma `Idempotency-Key` com o mesmo corpo, **quando** chega duas vezes, **então** a segunda devolve a resposta gravada sem novo efeito. Com corpo diferente, devolve `422`.
- **Dado** uma requisição sem JWT, **então** `401`; com JWT válido mas sem `tenant_id`, **então** `403 no_active_tenant`.

## Testes
- Teste de contrato: a API nunca usa `service_role` em rotas de usuário (verificado por fixture que inspeciona o papel da conexão).
- Teste de isolamento genérico reutilizável por todos os módulos.

## Dependências
{{#02}}, {{#03}}

<!-- issue: 08 -->
title: Contrato canônico de evento v1.0 (JSON Schema → Pydantic e TS)
labels: chore, backend, M03-ingestion, P0
---
## Contexto
O PRD §5 define o formato normalizado. Todos os conectores e a importação manual convergem para ele.

## Escopo
- `packages/contracts/schemas/event.v1.json` (JSON Schema 2020-12), com base no exemplo do PRD: `schema_version`, `event_id` (UUIDv7), `integration_id`, `execution_id?`, `trace_id?`, `timestamp`, `source{provider,service,resource}`, `operation`, `severity` (enum), `error{category,http_status,code,message}?`, `business_context{entity_type,entity_reference}?`, `attributes` (objeto, máximo de 64 chaves e 16 KB).
- **Sem `tenant_id`**: o schema rejeita a propriedade.
- Geração de modelos Pydantic (`datamodel-code-generator`) e tipos TS (`json-schema-to-typescript`). O CI falha se o gerado estiver desatualizado.
- Enum `error.category`: `TIMEOUT`, `AUTH`, `RATE_LIMIT`, `VALIDATION`, `BUSINESS_REJECTION`, `DUPLICATE`, `CONNECTIVITY`, `UNKNOWN`.
- Política de versionamento: mudança compatível sobe minor; incompatível cria `event.v2.json` e mantém o v1 aceito por 2 releases.
- Fixtures de exemplo (válidas e inválidas) em `packages/contracts/fixtures`.

## Critérios de aceite
- **Dado** um evento com `tenant_id`, **quando** é validado, **então** é rejeitado com erro claro.
- **Dado** as fixtures do PRD, **quando** são validadas em Python e TS, **então** os resultados são idênticos.

## Testes
- Testes property-based (Hypothesis) de ida e volta, serialização e validação.

## Dependências
{{#01}}

<!-- issue: 09 -->
title: App shell Next.js mobile first (PWA, navegação inferior, temas, pt-BR)
labels: feature, frontend, mobile, P0
---
## Contexto
O analista de plantão usa o celular. O PRD pede uma interface orientada à investigação, com poucos toques até a evidência.

## Escopo
- `apps/web`: Next.js (App Router), TypeScript, Tailwind e shadcn/ui, com tokens do kit de mockup (fundo `#0E1413`, acento `#2FBFAE`) e um tema claro equivalente.
- `@supabase/ssr` para a sessão (cookies). Middleware que redireciona para o login sem sessão e para o onboarding sem Organização.
- Layout responsivo:
  - < 768 px: barra inferior **Início · Incidentes · Execuções · Conectores · Mais**;
  - ≥ 1280 px: sidebar (ver mockups desktop).
- Componentes base: `Card`, `Chip` (severidade e status), `BottomSheet`, `KpiTile`, `ListItem`, `EmptyState`, `Skeleton`, `ErrorState`, `ConfidenceBar` (sempre com o rótulo "heurística").
- PWA: manifest, ícones, service worker (cache do shell, sem cache de dados de tenant) e instalável.
- i18n: pt-BR padrão (`next-intl`), com datas e números em `pt-BR` e horários no fuso do navegador.
- Acessibilidade: alvos ≥ 44 px, contraste AA, foco visível e `prefers-reduced-motion`.
- Cliente da API tipado (de {{#07}}) com React Query.

## UI
O padrão de todas as telas está no canvas (Tela 4 como referência de shell).

## Critérios de aceite
- Lighthouse mobile: PWA instalável, Acessibilidade ≥ 95, Performance ≥ 85 no shell.
- **Dado** 390 px, **quando** navego pelas 5 abas, **então** não há rolagem horizontal e a aba ativa fica destacada.
- **Dado** um logout, **quando** abro o PWA offline, **então** não aparece nenhum dado em cache de outro tenant.

## Testes
- Playwright com projetos `mobile-chrome` (Pixel 7) e `desktop`. Snapshots visuais dos componentes base.

## Dependências
{{#04}}, {{#07}}

<!-- issue: 10 -->
title: Cadastro de Integrações (CRUD) com Ambiente
labels: feature, frontend, backend, database, M01-org, mobile, P0
---
## Contexto
A Integração é o fluxo de negócio monitorado. Execuções, Incidentes e Conectores se ligam a ela (PRD §4, `POST/GET /integrations`).

## História de usuário
Como **Admin**, quero cadastrar as Integrações que minha equipe sustenta, para organizar a coleta e os incidentes por fluxo.

## Escopo
- Tabela `integrations` (DDL do PRD), com `description`, `owner_team`, `environment check in ('dev','hml','prd')`, `archived_at` e `unique (tenant_id, name, environment)`.
- `POST/GET/PATCH /api/v1/integrations`, `POST /api/v1/integrations/{id}/archive` (sem delete físico se houver Execuções).
- Tela 10: lista em cards com taxa de erro de 24 h (zero até {{#17}}) e formulário em bottom sheet.
- O onboarding termina sugerindo criar a primeira Integração.

## UI — Tela 10
```text
┌──────────────────────────┐
│ ← Integrações    [Nova]  │
│ ┌ Pedidos SF → SAP [prd]┐│
│ │ Taxa de erro 24h 4,1% ││
│ └───────────────────────┘│
│ ┌ Nova integração ──────┐│
│ │ Nome / Origem/Destino ││
│ │ Ambiente [Produção ▾] ││
│ └───────────────────────┘│
└──────────────────────────┘
```

## Critérios de aceite
- **Dado** um Analyst, **quando** tenta criar uma Integração, **então** `403`.
- **Dado** um nome e Ambiente duplicados no mesmo tenant, **então** `409`. Em outro tenant, o mesmo nome é permitido.
- **Dado** uma Integração arquivada, **então** ela some das listas padrão e seus Conectores param de sincronizar.

## Testes
- pgTAP de isolamento e FKs compostas: tentar referenciar a Integração de outro tenant falha no banco.

## Dependências
{{#06}}, {{#09}}
