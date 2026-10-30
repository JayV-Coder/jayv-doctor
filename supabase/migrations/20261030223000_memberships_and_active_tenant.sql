-- Ticket #5: Vínculos, Organização ativa e claims de tenant no JWT.

alter table public.tenants
  add column segment text check (char_length(segment) between 2 and 80),
  add column dpa_accepted_at timestamptz;

create table public.memberships (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role text not null check (role in ('owner', 'admin', 'analyst', 'viewer')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, user_id)
);
comment on table public.memberships is 'Vínculos: Usuário em uma Organização, com exatamente um Papel.';

create index memberships_user_id_idx on public.memberships (user_id);

create trigger memberships_set_updated_at
before update on public.memberships
for each row execute function app.set_updated_at();

-- A FK composta garante que só há Organização ativa com Vínculo; remover o Vínculo a apaga.
create table public.user_active_tenant (
  user_id uuid primary key references auth.users (id) on delete cascade,
  tenant_id uuid not null,
  updated_at timestamptz not null default now(),
  foreign key (tenant_id, user_id) references public.memberships (tenant_id, user_id) on delete cascade
);
comment on table public.user_active_tenant is 'Organização ativa de cada Usuário: origem das claims do JWT.';

create index user_active_tenant_tenant_id_idx on public.user_active_tenant (tenant_id, user_id);

create trigger user_active_tenant_set_updated_at
before update on public.user_active_tenant
for each row execute function app.set_updated_at();

alter table public.memberships enable row level security;
alter table public.user_active_tenant enable row level security;

-- Escrita só pelas funções abaixo: ninguém se vincula nem troca de tenant por escrita direta.
revoke all on public.memberships from anon, authenticated;
revoke all on public.user_active_tenant from anon, authenticated;
grant select on public.memberships to authenticated;
grant select on public.user_active_tenant to authenticated;

-- Os próprios Vínculos alimentam o seletor; os demais só aparecem na Organização ativa.
create policy memberships_select on public.memberships
for select to authenticated
using (user_id = (select auth.uid()) or tenant_id = (select app.current_tenant_id()));

create policy user_active_tenant_select_own on public.user_active_tenant
for select to authenticated
using (user_id = (select auth.uid()));

-- O seletor precisa do nome das Organizações do Usuário, não só da ativa.
create policy tenants_select_member on public.tenants
for select to authenticated
using (
  exists (
    select 1 from public.memberships m
    where m.tenant_id = tenants.id and m.user_id = (select auth.uid())
  )
);

-- security definer: supabase_auth_admin não lê estas tabelas, por causa do RLS.
create function app.custom_access_token_hook(event jsonb)
returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $$
declare
  claims jsonb := coalesce(event -> 'claims', '{}') - 'tenant_id' - 'tenant_role';
  active_tenant uuid;
  active_role text;
begin
  select m.tenant_id, m.role into active_tenant, active_role
  from public.user_active_tenant a
  join public.memberships m on m.tenant_id = a.tenant_id and m.user_id = a.user_id
  where a.user_id = (event ->> 'user_id')::uuid;

  if active_tenant is not null then
    claims := claims || jsonb_build_object('tenant_id', active_tenant, 'tenant_role', active_role);
  end if;
  return jsonb_set(event, '{claims}', claims);
end;
$$;

revoke all on function app.custom_access_token_hook(jsonb) from public, authenticated, service_role;
grant usage on schema app to supabase_auth_admin;
grant execute on function app.custom_access_token_hook(jsonb) to supabase_auth_admin;

-- security definer: criar Organização, Vínculo Owner e Organização ativa é uma coisa só,
-- e o `authenticated` não escreve em nenhuma das três tabelas. Quem cria aceita o DPA.
create function app.create_organization(name text, slug text, segment text, llm_provider text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  user_id uuid := auth.uid();
  new_tenant uuid;
begin
  if user_id is null then
    raise insufficient_privilege using message = 'sessão obrigatória';
  end if;
  insert into public.tenants (name, slug, segment, llm_provider, dpa_accepted_at)
  values (name, slug, segment, llm_provider, now())
  returning id into new_tenant;
  insert into public.memberships (tenant_id, user_id, role) values (new_tenant, user_id, 'owner');
  insert into public.user_active_tenant (user_id, tenant_id) values (user_id, new_tenant)
  on conflict on constraint user_active_tenant_pkey do update set tenant_id = excluded.tenant_id;
  return new_tenant;
end;
$$;

-- security definer: o `authenticated` não escreve em user_active_tenant.
create function app.switch_organization(target uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  user_id uuid := auth.uid();
begin
  if not exists (
    select 1 from public.memberships m where m.tenant_id = target and m.user_id = auth.uid()
  ) then
    raise insufficient_privilege using message = 'sem Vínculo com a Organização';
  end if;
  insert into public.user_active_tenant (user_id, tenant_id) values (user_id, target)
  on conflict on constraint user_active_tenant_pkey do update set tenant_id = excluded.tenant_id;
end;
$$;

revoke all on function app.create_organization(text, text, text, text) from public, service_role;
revoke all on function app.switch_organization(uuid) from public, service_role;
grant execute on function app.create_organization(text, text, text, text) to authenticated;
grant execute on function app.switch_organization(uuid) to authenticated;
