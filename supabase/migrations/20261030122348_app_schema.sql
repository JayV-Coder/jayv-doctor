-- Convenções multi-tenant (ADR-0004): o tenant vem só do JWT e toda política de RLS
-- passa pelos helpers do schema `app`, que não é exposto pela API de dados.
create schema app;
comment on schema app is 'Helpers de tenancy e RLS. Não exposto pelo PostgREST.';
revoke all on schema app from public;
grant usage on schema app to authenticated, service_role;

-- Organização ativa: claim `tenant_id` emitida pelo Custom Access Token Hook (ticket #5).
create function app.current_tenant_id()
returns uuid
language sql
stable
set search_path = ''
as $$
  select nullif(auth.jwt() ->> 'tenant_id', '')::uuid
$$;

-- Papel do Usuário na Organização ativa: owner, admin, analyst ou viewer.
create function app.current_tenant_role()
returns text
language sql
stable
set search_path = ''
as $$
  select nullif(auth.jwt() ->> 'tenant_role', '')
$$;

create function app.has_role(variadic roles text[])
returns boolean
language sql
stable
set search_path = ''
as $$
  select coalesce(app.current_tenant_role() = any (roles), false)
$$;

create function app.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

revoke all on all functions in schema app from public;
grant execute on all functions in schema app to authenticated, service_role;

-- Organizações. Criação, plano e status mudam só pela API (service_role).
create table public.tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null check (char_length(name) between 2 and 120),
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$'),
  plan text not null default 'pilot' check (plan in ('pilot', 'professional', 'enterprise')),
  llm_provider text not null default 'anthropic' check (llm_provider in ('anthropic', 'vertex')),
  status text not null default 'active' check (status in ('active', 'suspended', 'deleted')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
comment on table public.tenants is 'Organizações clientes: a unidade de isolamento de dados.';

create trigger tenants_set_updated_at
before update on public.tenants
for each row execute function app.set_updated_at();

alter table public.tenants enable row level security;

revoke all on public.tenants from anon, authenticated;
grant select on public.tenants to authenticated;
grant update (name) on public.tenants to authenticated;

create policy tenants_select_own on public.tenants
for select to authenticated
using (id = (select app.current_tenant_id()));

create policy tenants_update_by_admin on public.tenants
for update to authenticated
using (id = (select app.current_tenant_id()) and (select app.has_role('owner', 'admin')))
with check (id = (select app.current_tenant_id()));
