begin;
\ir ../helpers/tenancy.psql
select plan(12);

select has_schema('app');
select has_function('app', 'current_tenant_id', array[]::text[]);
select has_function('app', 'current_tenant_role', array[]::text[]);
select has_function('app', 'has_role', array['text[]']);
select has_function('app', 'set_updated_at', array[]::text[]);
select is((select count(*)::int from pg_extension where extname = 'vector'), 1, 'pgvector instalado');

select tests.clear_authentication();
select is(app.current_tenant_id(), null, 'sem JWT não há Organização ativa');
select is(app.has_role('owner', 'admin', 'analyst', 'viewer'), false, 'sem JWT nenhum Papel vale');

select tests.authenticate_as(
  '00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-0000000000aa', 'analyst'
);
select is(app.current_tenant_id(), '00000000-0000-4000-8000-0000000000aa'::uuid, 'lê tenant_id do JWT');
select is(app.current_tenant_role(), 'analyst', 'lê tenant_role do JWT');
select is(app.has_role('owner', 'admin'), false, 'analyst não é owner/admin');
select is(app.has_role('analyst', 'viewer'), true, 'analyst está na lista');

select * from finish();
rollback;
