begin;
\ir ../helpers/tenancy.psql
select plan(15);

-- Acme e Varejo são Organizações distintas; Ana pertence à Acme.
select tests.create_tenant('00000000-0000-4000-8000-00000000ac01', 'acme');
select tests.create_tenant('00000000-0000-4000-8000-00000000be01', 'varejo');
select tests.create_user('00000000-0000-4000-8000-0000000a0001', 'ana@acme.test');

select policies_are('public', 'tenants', array['tenants_select_member', 'tenants_select_own', 'tenants_update_by_admin']);
select is(
  (select relrowsecurity from pg_class where oid = 'public.tenants'::regclass), true, 'RLS ligado em tenants'
);

-- Analyst da Acme: vê só a própria Organização e não a renomeia.
select tests.authenticate_as('00000000-0000-4000-8000-0000000a0001', '00000000-0000-4000-8000-00000000ac01', 'analyst');
select results_eq(
  'select id from public.tenants',
  $$values ('00000000-0000-4000-8000-00000000ac01'::uuid)$$,
  'analyst vê só a Organização ativa'
);
update public.tenants set name = 'Hackeado' where id = '00000000-0000-4000-8000-00000000ac01';
select tests.clear_authentication();
select is(
  (select name from public.tenants where id = '00000000-0000-4000-8000-00000000ac01'), 'Acme',
  'analyst não renomeia a Organização'
);

-- Admin sem MFA verificado (aal1) não executa ação administrativa.
select tests.authenticate_as('00000000-0000-4000-8000-0000000a0001', '00000000-0000-4000-8000-00000000ac01', 'admin');
update public.tenants set name = 'Sem MFA' where id = '00000000-0000-4000-8000-00000000ac01';
select tests.clear_authentication();
select is(
  (select name from public.tenants where id = '00000000-0000-4000-8000-00000000ac01'), 'Acme',
  'admin em aal1 não renomeia a Organização (MFA obrigatório)'
);
select has_function('app', 'current_aal', array[]::text[]);

-- Admin com MFA (aal2): renomeia a própria, não a dos outros.
select tests.authenticate_as('00000000-0000-4000-8000-0000000a0001', '00000000-0000-4000-8000-00000000ac01', 'admin', 'aal2');
update public.tenants set name = 'Acme Consultoria' where id = '00000000-0000-4000-8000-00000000ac01';
update public.tenants set name = 'Invadida' where id = '00000000-0000-4000-8000-00000000be01';
select tests.clear_authentication();
select is(
  (select name from public.tenants where id = '00000000-0000-4000-8000-00000000ac01'), 'Acme Consultoria',
  'admin renomeia a própria Organização'
);
select is(
  (select name from public.tenants where id = '00000000-0000-4000-8000-00000000be01'), 'Varejo',
  'admin não altera outra Organização'
);

-- Mesmo um admin com MFA não muda plano, não cria nem apaga Organização direto.
select tests.authenticate_as('00000000-0000-4000-8000-0000000a0001', '00000000-0000-4000-8000-00000000ac01', 'admin', 'aal2');
select throws_ok(
  $$update public.tenants set plan = 'enterprise' where id = '00000000-0000-4000-8000-00000000ac01'$$,
  '42501', null, 'plano não é editável pelo cliente'
);
select throws_ok(
  $$insert into public.tenants (name, slug) values ('Nova', 'nova')$$,
  '42501', null, 'cliente não cria Organização direto (passa pela API)'
);
select throws_ok(
  $$delete from public.tenants where id = '00000000-0000-4000-8000-00000000ac01'$$,
  '42501', null, 'cliente não apaga Organização'
);

-- Sem Organização ativa, nada é visível; anon não tem acesso algum.
select tests.authenticate_without_tenant('00000000-0000-4000-8000-0000000a0001');
select is_empty('select 1 from public.tenants', 'sem tenant_id no JWT nada é visível');
select tests.authenticate_as_anon();
select throws_ok('select 1 from public.tenants', '42501', null, 'anon não lê tenants');

-- updated_at é do servidor: o trigger ignora o valor enviado.
select tests.clear_authentication();
update public.tenants set updated_at = '2000-01-01', name = 'Acme'
where id = '00000000-0000-4000-8000-00000000ac01';
select is(
  (select updated_at from public.tenants where id = '00000000-0000-4000-8000-00000000ac01'), now(),
  'trigger define updated_at'
);
select has_trigger('public', 'tenants', 'tenants_set_updated_at', 'trigger de updated_at em tenants');

select * from finish();
rollback;
