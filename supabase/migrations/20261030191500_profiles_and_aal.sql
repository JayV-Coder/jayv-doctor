-- Ticket #4: perfil do Usuário (1:1 com auth.users) e MFA obrigatório em ações administrativas.

-- Nível de garantia da sessão: aal1 (senha, link, OAuth) ou aal2 (MFA verificado).
create function app.current_aal()
returns text
language sql
stable
set search_path = ''
as $$
  select nullif(auth.jwt() ->> 'aal', '')
$$;

revoke all on function app.current_aal() from public;
grant execute on function app.current_aal() to authenticated, service_role;

-- Owner e Admin só administram com MFA verificado.
alter policy tenants_update_by_admin on public.tenants
using (
  id = (select app.current_tenant_id())
  and (select app.has_role('owner', 'admin'))
  and (select app.current_aal()) = 'aal2'
);

-- Excluir o usuário apaga o perfil em cascata (LGPD).
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text check (char_length(full_name) <= 120),
  avatar_url text check (avatar_url ~ '^https://' and char_length(avatar_url) <= 2048),
  locale text not null default 'pt-BR' check (locale ~ '^[a-z]{2}(-[A-Z]{2})?$'),
  created_at timestamptz not null default now()
);
comment on table public.profiles is 'Perfil do Usuário: dados pessoais, sem relação com tenant.';

alter table public.profiles enable row level security;

revoke all on public.profiles from anon, authenticated;
grant select on public.profiles to authenticated;
grant update (full_name, avatar_url, locale) on public.profiles to authenticated;

create policy profiles_select_own on public.profiles
for select to authenticated
using (id = (select auth.uid()));

create policy profiles_update_own on public.profiles
for update to authenticated
using (id = (select auth.uid()))
with check (id = (select auth.uid()));

-- security definer: roda como supabase_auth_admin, que não tem acesso a public.profiles.
-- Os metadados vêm do provedor, então são saneados em vez de quebrar o cadastro.
create function app.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  avatar text := coalesce(new.raw_user_meta_data ->> 'avatar_url', new.raw_user_meta_data ->> 'picture');
begin
  insert into public.profiles (id, full_name, avatar_url)
  values (
    new.id,
    left(coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name'), 120),
    case when avatar ~ '^https://' and char_length(avatar) <= 2048 then avatar end
  );
  return new;
end;
$$;

revoke all on function app.handle_new_user() from public, authenticated, service_role;

create trigger on_auth_user_created
after insert on auth.users
for each row execute function app.handle_new_user();
