# Convenções do banco (Supabase Postgres)

Base: [ADR-0004](../docs/adr/0004-isolamento-multi-tenant-rls-e-fks-compostas.md). O tenant vem **só** do JWT (claim `tenant_id`, emitida pelo Custom Access Token Hook) e toda política passa pelos helpers do schema `app`.

## Helpers (`app`, não exposto pelo PostgREST)

| Função | Retorna |
|---|---|
| `app.current_tenant_id()` | `uuid` da Organização ativa, ou `null` sem claim |
| `app.current_tenant_role()` | `owner` · `admin` · `analyst` · `viewer`, ou `null` |
| `app.has_role(variadic text[])` | `true` se o Papel ativo está na lista |
| `app.set_updated_at()` | trigger `before update` que define `updated_at = now()` |

Nas políticas, envolva os helpers em `(select …)` para o Postgres avaliar uma vez por consulta, não por linha:

```sql
using (tenant_id = (select app.current_tenant_id()))
```

## Checklist de tabela nova

- [ ] `tenant_id uuid not null references public.tenants (id)` e `unique (tenant_id, id)`
- [ ] FKs para outras tabelas de tenant são **compostas**: `foreign key (tenant_id, x_id) references x (tenant_id, id)`
- [ ] `alter table … enable row level security` e políticas por operação e Papel
- [ ] `revoke all … from anon, authenticated` seguido só dos `grant` necessários (de coluna, quando couber)
- [ ] índices começam por `tenant_id`
- [ ] `updated_at` com o trigger `app.set_updated_at()`
- [ ] teste pgTAP de isolamento em `tests/database/`: outro tenant não lê, não altera e não referencia
- [ ] funções com `set search_path = ''` e nomes qualificados; `security definer` só com justificativa e `revoke execute … from public`

## Migrações

- Fonte única: `supabase/migrations/<versão>_<nome>.sql`. Nunca edite uma migração já aplicada; crie outra.
- A versão do arquivo é a mesma registrada em `supabase_migrations.schema_migrations` do projeto, para o `supabase db push` não divergir.

## Testes

- `make db:test` roda `supabase test db` (pgTAP) na stack local. Os testes incluem `tests/helpers/tenancy.psql`, que oferece:
  - `tests.authenticate_as(user, tenant, role)`;
  - `tests.authenticate_without_tenant(user)`;
  - `tests.authenticate_as_anon()`;
  - `tests.clear_authentication()`;
  - `tests.create_tenant(id, slug)` e `tests.create_user(id, email)`.
- Num projeto hospedado (sem psql), `python3 scripts/run-pgtap-remote.py <teste>` gera um SQL único que roda o teste numa transação sem commit e devolve a saída TAP.
