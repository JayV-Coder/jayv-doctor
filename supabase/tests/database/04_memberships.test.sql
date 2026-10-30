begin;
\ir ../helpers/tenancy.psql
select plan(29);

select has_table('public', 'memberships', 'tabela public.memberships existe');
select has_table('public', 'user_active_tenant', 'tabela public.user_active_tenant existe');
select is(
  (select relrowsecurity from pg_class where oid = 'public.memberships'::regclass), true, 'RLS ligado em memberships'
);
select is(
  (select relrowsecurity from pg_class where oid = 'public.user_active_tenant'::regclass), true,
  'RLS ligado em user_active_tenant'
);

select tests.create_user('00000000-0000-4000-8000-0000000a0001', 'ana@acme.test');
select tests.create_user('00000000-0000-4000-8000-0000000b0001', 'bruno@varejo.test');
select tests.create_tenant('00000000-0000-4000-8000-00000000ac01', 'acme');
select tests.create_tenant('00000000-0000-4000-8000-00000000be01', 'varejo-brasil');
select tests.create_tenant('00000000-0000-4000-8000-00000000cc01', 'industria-meridional');

insert into public.memberships (tenant_id, user_id, role) values
  ('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000a0001', 'owner'),
  ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000a0001', 'viewer'),
  ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000b0001', 'admin');

select throws_ok(
  $$insert into public.memberships (tenant_id, user_id, role)
    values ('00000000-0000-4000-8000-00000000cc01', '00000000-0000-4000-8000-0000000a0001', 'root')$$,
  '23514', null, 'Papel fora da lista é recusado'
);
select throws_ok(
  $$insert into public.user_active_tenant (user_id, tenant_id)
    values ('00000000-0000-4000-8000-0000000a0001', '00000000-0000-4000-8000-00000000cc01')$$,
  '23503', null, 'Organização ativa exige Vínculo'
);

-- Custom Access Token Hook
insert into public.user_active_tenant (user_id, tenant_id)
values ('00000000-0000-4000-8000-0000000a0001', '00000000-0000-4000-8000-00000000ac01');

create function tests.hook_claims(user_id uuid, claims jsonb default '{"role": "authenticated"}')
returns jsonb
language sql
as $$
  select app.custom_access_token_hook(jsonb_build_object('user_id', user_id, 'claims', claims)) -> 'claims'
$$;

select is(
  tests.hook_claims('00000000-0000-4000-8000-0000000a0001') ->> 'tenant_id',
  '00000000-0000-4000-8000-00000000ac01', 'hook injeta o tenant ativo'
);
select is(
  tests.hook_claims('00000000-0000-4000-8000-0000000a0001') ->> 'tenant_role', 'owner', 'hook injeta o Papel do Vínculo'
);
select is(
  tests.hook_claims('00000000-0000-4000-8000-0000000a0001') ->> 'role', 'authenticated', 'hook preserva as demais claims'
);
select is(
  tests.hook_claims(
    '00000000-0000-4000-8000-0000000b0001',
    '{"role": "authenticated", "tenant_id": "00000000-0000-4000-8000-00000000ac01", "tenant_role": "owner"}'
  ) ->> 'tenant_id',
  null, 'sem Organização ativa, claims antigas de tenant somem'
);

select is(
  has_function_privilege('authenticated', 'app.custom_access_token_hook(jsonb)', 'execute'), false,
  'authenticated não executa o hook'
);
select is(
  has_function_privilege('supabase_auth_admin', 'app.custom_access_token_hook(jsonb)', 'execute'), true,
  'supabase_auth_admin executa o hook'
);

-- Isolamento
select tests.authenticate_as(
  '00000000-0000-4000-8000-0000000a0001', '00000000-0000-4000-8000-00000000ac01', 'owner', 'aal2'
);
select results_eq(
  $$select slug from public.tenants$$,
  $$values ('acme'::text)$$,
  'em public.tenants, o Usuário só lê a Organização ativa'
);
select results_eq(
  $$select slug, role from app.list_organizations() order by slug$$,
  $$values ('acme'::text, 'owner'::text), ('varejo-brasil'::text, 'viewer'::text)$$,
  'o seletor lista as Organizações com Vínculo, e não as outras'
);
select results_eq(
  $$select count(*)::int from public.memberships where tenant_id <> app.current_tenant_id()$$,
  $$values (0)$$,
  'Vínculos fora da Organização ativa ficam ocultos, mesmo os próprios'
);
select results_eq(
  $$select tenant_id::text from public.memberships where user_id <> auth.uid()$$,
  $$select null::text where false$$,
  'Vínculos de outras pessoas em Organização não ativa ficam ocultos'
);
select lives_ok(
  $$select app.switch_organization('00000000-0000-4000-8000-00000000be01')$$, 'troca para Organização com Vínculo'
);
select throws_ok(
  $$select app.switch_organization('00000000-0000-4000-8000-00000000cc01')$$,
  '42501', null, 'troca sem Vínculo é recusada'
);
select results_eq(
  $$select tenant_id::text from public.user_active_tenant$$,
  $$values ('00000000-0000-4000-8000-00000000be01'::text)$$,
  'a troca recusada não muda a Organização ativa'
);
select throws_ok(
  $$update public.user_active_tenant set tenant_id = '00000000-0000-4000-8000-00000000ac01'$$,
  '42501', null, 'Organização ativa não muda por escrita direta'
);
select throws_ok(
  $$insert into public.memberships (tenant_id, user_id, role)
    values ('00000000-0000-4000-8000-00000000cc01', auth.uid(), 'owner')$$,
  '42501', null, 'Usuário não cria Vínculo por escrita direta'
);

select tests.authenticate_as(
  '00000000-0000-4000-8000-0000000b0001', '00000000-0000-4000-8000-00000000be01', 'admin', 'aal2'
);
select is(
  (select count(*)::int from public.memberships), 2, 'na Organização ativa, o Usuário vê todos os Vínculos dela'
);
select is(
  (select count(*)::int from public.user_active_tenant), 0, 'Organização ativa de outra pessoa fica oculta'
);

-- Criação de Organização
select tests.authenticate_without_tenant('00000000-0000-4000-8000-0000000b0001');
select lives_ok(
  $$select app.create_organization('Nova Org', 'nova-org', 'Varejo', 'vertex')$$, 'cria a Organização'
);
select tests.clear_authentication();
select results_eq(
  $$select m.role, t.llm_provider, t.dpa_accepted_at is not null, a.tenant_id = t.id
    from public.tenants t
    join public.memberships m on m.tenant_id = t.id
    join public.user_active_tenant a on a.user_id = m.user_id
    where t.slug = 'nova-org' and m.user_id = '00000000-0000-4000-8000-0000000b0001'$$,
  $$values ('owner'::text, 'vertex'::text, true, true)$$,
  'quem cria vira Owner, aceita o DPA e passa a agir na nova Organização'
);

-- Remover o Vínculo tira as claims na renovação seguinte.
delete from public.memberships
where tenant_id = '00000000-0000-4000-8000-00000000be01' and user_id = '00000000-0000-4000-8000-0000000a0001';
select is(
  tests.hook_claims('00000000-0000-4000-8000-0000000a0001') ->> 'tenant_id', null,
  'Vínculo removido: as claims de tenant somem'
);

-- Organização que não está ativa na plataforma não emite claims nem aceita troca.
update public.tenants set status = 'suspended' where slug = 'nova-org';
select is(
  tests.hook_claims('00000000-0000-4000-8000-0000000b0001') ->> 'tenant_id', null,
  'Organização suspensa: as claims de tenant somem'
);
select tests.authenticate_without_tenant('00000000-0000-4000-8000-0000000b0001');
select results_eq(
  $$select slug from app.list_organizations()$$,
  $$values ('varejo-brasil'::text)$$,
  'Organização suspensa sai do seletor'
);
select throws_ok(
  $$select app.switch_organization((select id from public.tenants where slug = 'nova-org'))$$,
  '42501', null, 'troca para Organização suspensa é recusada'
);

select * from finish();
rollback;
