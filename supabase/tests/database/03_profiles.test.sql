begin;
\ir ../helpers/tenancy.psql
select plan(11);

select has_table('public', 'profiles', 'tabela public.profiles existe');
select is(
  (select relrowsecurity from pg_class where oid = 'public.profiles'::regclass), true, 'RLS ligado em profiles'
);

-- O trigger em auth.users cria o perfil a partir dos metadados do provedor.
select tests.create_user(
  '00000000-0000-4000-8000-0000000a0001', 'ana@acme.test',
  '{"full_name": "Ana Souza", "avatar_url": "https://lh3.example/ana.png"}'
);
select tests.create_user(
  '00000000-0000-4000-8000-0000000b0001', 'bruno@varejo.test',
  jsonb_build_object('full_name', repeat('x', 300), 'avatar_url', 'javascript:alert(1)')
);
select results_eq(
  $$select full_name, avatar_url, locale from public.profiles where id = '00000000-0000-4000-8000-0000000a0001'$$,
  $$values ('Ana Souza'::text, 'https://lh3.example/ana.png'::text, 'pt-BR'::text)$$,
  'perfil criado com nome, avatar e locale pt-BR'
);
select is(
  (select char_length(full_name) from public.profiles where id = '00000000-0000-4000-8000-0000000b0001'), 120,
  'nome longo do provedor é truncado em vez de impedir o cadastro'
);
select is(
  (select avatar_url from public.profiles where id = '00000000-0000-4000-8000-0000000b0001'), null,
  'avatar que não é https é descartado'
);

-- Cada usuário vê e edita só o próprio perfil.
select tests.authenticate_without_tenant('00000000-0000-4000-8000-0000000a0001');
select results_eq(
  'select id from public.profiles',
  $$values ('00000000-0000-4000-8000-0000000a0001'::uuid)$$,
  'usuário vê só o próprio perfil'
);
update public.profiles set full_name = 'Ana S.' where id = '00000000-0000-4000-8000-0000000a0001';
update public.profiles set full_name = 'Invadido' where id = '00000000-0000-4000-8000-0000000b0001';
select throws_ok(
  $$update public.profiles set id = gen_random_uuid() where id = '00000000-0000-4000-8000-0000000a0001'$$,
  '42501', null, 'id do perfil não é editável'
);
select tests.clear_authentication();
select is(
  (select full_name from public.profiles where id = '00000000-0000-4000-8000-0000000a0001'), 'Ana S.',
  'usuário edita o próprio nome'
);
select isnt(
  (select full_name from public.profiles where id = '00000000-0000-4000-8000-0000000b0001'), 'Invadido',
  'usuário não edita o perfil de outro'
);

select tests.authenticate_as_anon();
select throws_ok('select 1 from public.profiles', '42501', null, 'anon não lê perfis');

-- Excluir o usuário remove o perfil (LGPD).
select tests.clear_authentication();
delete from auth.users where id = '00000000-0000-4000-8000-0000000a0001';
select is_empty(
  $$select 1 from public.profiles where id = '00000000-0000-4000-8000-0000000a0001'$$,
  'perfil some junto com o usuário'
);

select * from finish();
rollback;
