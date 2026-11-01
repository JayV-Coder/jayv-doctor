-- SÓ NA STACK LOCAL E NO CI: nunca aplicar no projeto hospedado (ADR-0009).
-- As tabelas de `public` são do jayv-coder. Este arquivo copia o mínimo delas, para o Doctor rodar
-- localmente, e não faz nada se já existirem. Cópia de exvsozyemolrjbjetqww em 2026-11-01.
do $stub$
begin
  if to_regclass('public.organizations') is not null then
    return;
  end if;

  create table public.organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null check (char_length(btrim(name)) between 1 and 80),
    slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$'),
    created_by uuid references auth.users (id) on delete set null,
    created_at timestamptz not null default now()
  );

  create table public.organization_members (
    org_id uuid not null references public.organizations (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    role text not null check (role in ('owner', 'maintainer', 'member')),
    joined_at timestamptz not null default now(),
    primary key (org_id, user_id)
  );

  create table public.profiles (
    user_id uuid primary key references auth.users (id) on delete cascade,
    display_name text not null,
    username text not null unique,
    avatar_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
  );

  alter table public.organizations enable row level security;
  alter table public.organization_members enable row level security;
  alter table public.profiles enable row level security;

  revoke all on public.organizations, public.organization_members, public.profiles from anon, authenticated;
  grant select on public.organizations, public.organization_members, public.profiles to authenticated;
  grant update on public.profiles to authenticated;

  create function public.org_role(org uuid)
  returns text
  language sql
  stable
  security definer
  set search_path = ''
  as $fn$
    select role from public.organization_members where org_id = org and user_id = auth.uid();
  $fn$;

  create function public.second_factor_ok()
  returns boolean
  language sql
  stable
  security definer
  set search_path = ''
  as $fn$
    select auth.uid() is null
      or coalesce(auth.jwt() ->> 'aal', 'aal1') = 'aal2'
      or not exists (
        select 1 from auth.mfa_factors f where f.user_id = auth.uid() and f.status::text = 'verified'
      );
  $fn$;

  create policy "membro lê" on public.organizations
  for select to public using ((select public.org_role(organizations.id)) is not null);
  create policy "segundo fator" on public.organizations
  as restrictive for all to public using ((select public.second_factor_ok()));

  create policy "membro lê" on public.organization_members
  for select to public using ((select public.org_role(organization_members.org_id)) is not null);
  create policy "segundo fator" on public.organization_members
  as restrictive for all to public using ((select public.second_factor_ok()));

  create policy "dono lê" on public.profiles
  for select to public using (user_id = (select auth.uid()));
  create policy "dono muda" on public.profiles
  for update to public using (user_id = (select auth.uid()));
  create policy "segundo fator" on public.profiles
  as restrictive for all to public using ((select public.second_factor_ok()));

  create function public.create_organization(name text, slug text)
  returns uuid
  language plpgsql
  security definer
  set search_path = ''
  as $fn$
  declare
    org uuid;
  begin
    if auth.uid() is null then raise exception 'org.forbidden'; end if;
    if exists (select 1 from public.organizations o where o.slug = lower(btrim(create_organization.slug))) then
      raise exception 'org.slugTaken';
    end if;
    insert into public.organizations (name, slug, created_by)
    values (btrim(name), lower(btrim(slug)), auth.uid()) returning id into org;
    insert into public.organization_members (org_id, user_id, role) values (org, auth.uid(), 'owner');
    return org;
  end;
  $fn$;

  create function public.profiles_create()
  returns trigger
  language plpgsql
  security definer
  set search_path = ''
  as $fn$
  begin
    insert into public.profiles (user_id, display_name, username)
    values (
      new.id,
      coalesce(new.raw_user_meta_data ->> 'full_name', split_part(new.email, '@', 1)),
      new.id::text
    )
    on conflict (user_id) do nothing;
    return new;
  end;
  $fn$;

  create trigger profiles_create
  after insert on auth.users
  for each row execute function public.profiles_create();
end;
$stub$;
