# Convenções do banco (Supabase Postgres)

Base: [ADR-0004](../docs/adr/0004-isolamento-multi-tenant-rls-e-fks-compostas.md). O tenant vem **só** do JWT (claim `tenant_id`, emitida pelo Custom Access Token Hook) e toda política passa pelos helpers do schema `doctor`. O projeto é compartilhado com o jayv-coder: nada do Doctor é criado em `public` ([ADR-0009](../docs/adr/0009-doctor-no-projeto-supabase-do-jayv-coder.md)).

## Helpers (`doctor`, não exposto pelo PostgREST)

| Função | Retorna |
|---|---|
| `doctor.current_tenant_id()` | `uuid` da Organização ativa, ou `null` sem claim |
| `doctor.current_tenant_role()` | `owner` · `admin` · `analyst` · `viewer`, ou `null` |
| `doctor.has_role(variadic text[])` | `true` se o Papel ativo está na lista |
| `doctor.current_aal()` | `aal1` ou `aal2` (MFA verificado), ou `null`; ações administrativas exigem `aal2` |
| `doctor.create_organization(name, slug, segment, llm_provider)` | cria Organização, Vínculo Owner e Organização ativa; `authenticated` só escreve nessas tabelas por aqui |
| `doctor.list_organizations()` | Organizações ativas do Usuário, com o Papel: só para o seletor |
| `doctor.switch_organization(target)` | troca a Organização ativa; `42501` sem Vínculo |
| `doctor.require_manager()` | só para funções: exige Owner ou Admin com `aal2`, com o Papel **lido da tabela**, não do JWT |
| `doctor.is_manager()` | `true` para Owner ou Admin com `aal2`, com o Papel **lido da tabela**: para políticas de escrita |
| `doctor.set_updated_at()` | trigger `before update` que define `updated_at = now()` |

Nas políticas, envolva os helpers em `(select …)` para o Postgres avaliar uma vez por consulta, não por linha:

```sql
using (tenant_id = (select doctor.current_tenant_id()))
```

## Checklist de tabela nova

- [ ] `tenant_id uuid not null references doctor.tenants (id)` e `unique (tenant_id, id)`
- [ ] FKs para outras tabelas de tenant são **compostas**: `foreign key (tenant_id, x_id) references x (tenant_id, id)`
- [ ] `alter table … enable row level security` e políticas por operação e Papel
- [ ] `revoke all … from anon, authenticated` seguido só dos `grant` necessários (de coluna, quando couber)
- [ ] índices começam por `tenant_id`
- [ ] `updated_at` com o trigger `doctor.set_updated_at()`
- [ ] teste pgTAP de isolamento em `tests/database/`: outro tenant não lê, não altera e não referencia
- [ ] funções com `set search_path = ''` e nomes qualificados; `security definer` só com justificativa e `revoke execute … from public`

## API

- `core` é a plataforma (auth, `tenant_tx`, erros, idempotência, rate limit, telemetria); cada módulo tem `router.py`, `service.py` e `repo.py` e só importa `core`. `uv run lint-imports` barra o resto.
- Novo módulo: crie o pacote em `aid_api/`, inclua no contrato de `pyproject.toml` e use `route_class=IdempotentRoute` com as dependências `rate_limit` e `idempotency`.

## Migrações

- Fonte única: `supabase/migrations/<versão>_<nome>.sql`. Nunca edite uma migração já aplicada; crie outra.
- Não entram em `supabase_migrations.schema_migrations`, que é do jayv-coder: ver [environments.md](../docs/operations/environments.md).
- `00000000000000_shared_public_stub.sql` é só da stack local e do CI.

## Testes

- `make db:test` roda `supabase test db` (pgTAP) na stack local. Os testes incluem `tests/helpers/tenancy.psql`, que oferece:
  - `tests.authenticate_as(user, tenant, role, aal)`, com `aal` padrão `aal1`;
  - `tests.authenticate_without_tenant(user)`;
  - `tests.authenticate_as_anon()`;
  - `tests.clear_authentication()`;
  - `tests.create_tenant(id, slug)`, `tests.add_member(tenant, user, role)` e `tests.create_user(id, email, metadata)`.
- Testes rodam só na stack local: o único projeto hospedado tem dados reais do jayv-coder.
- O inventário `30_conventions.test.sql` reprova tabela nova sem RLS, sem `tenant_id`, sem `unique (tenant_id, id)` ou com FK não composta, e função `security definer` sem `search_path` fixo ou executável por `public`. Exceção nova entra na lista do teste, com o motivo. A matriz `31_isolation_matrix.test.sql` cobre toda tabela com `tenant_id` sozinha: inclua uma linha de B para a tabela nova na fixture.
