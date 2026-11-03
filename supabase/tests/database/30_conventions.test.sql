-- Inventário automático (ticket #27): tabela nova do schema doctor fora das convenções
-- (supabase/CONVENTIONS.md, ADR-0004) quebra o CI. Cada exceção tem o motivo ao lado.
begin;
select plan(10);

create temporary table tenant_tables as
select c.oid, c.relname
from pg_class c
where c.relnamespace = 'doctor'::regnamespace and c.relkind in ('r', 'p') and not c.relispartition;

create temporary table exceptions (relname name primary key, reason text not null);
insert into exceptions values
  ('tenants', 'é a própria Organização (id = tenant)'),
  ('global_knowledge_documents', 'Base global, comum a todas, só leitura'),
  ('global_knowledge_chunks', 'Base global, comum a todas, só leitura'),
  ('rule_definitions', 'catálogo global das Regras versionadas'),
  ('schema_migrations', 'controle das migrações do Doctor (ADR-0009)');

-- Sem `unique (tenant_id, id)`, com o motivo: a chave delas é outra.
create temporary table keyless (relname name primary key, reason text not null);
insert into keyless values
  ('events', 'particionada: a chave inclui a partição, (tenant_id, id, timestamp)'),
  ('execution_stats_dirty', 'fila de horas a recalcular: (tenant_id, integration_id, hour)'),
  ('incident_counters', 'um contador por Organização: tenant_id é a chave'),
  ('user_active_tenant', 'uma Organização ativa por Usuário: user_id é a chave');

select is(
  (select array_agg(relname order by relname) from tenant_tables t
   where not (select relrowsecurity from pg_class where oid = t.oid)),
  null, 'toda tabela do schema doctor tem RLS'
);

select is(
  (select array_agg(relname order by relname) from tenant_tables t
   where t.relname not in (select relname from exceptions)
     and not exists (select 1 from pg_attribute a
                     where a.attrelid = t.oid and a.attname = 'tenant_id' and not a.attisdropped)),
  null, 'toda tabela de tenant tem tenant_id'
);

select is(
  (select array_agg(relname order by relname) from tenant_tables t
   where t.relname not in (select relname from exceptions)
     and t.relname not in (select relname from keyless)
     and not exists (
       select 1 from pg_constraint k
       where k.conrelid = t.oid and k.contype in ('u', 'p')
         and (select array_agg(a.attname::text order by a.attname) from pg_attribute a
              where a.attrelid = t.oid and a.attnum = any(k.conkey)) = array['id', 'tenant_id'])),
  null, 'toda tabela de tenant tem unique (tenant_id, id)'
);

select is(
  (select array_agg(k.conname::text order by k.conname)
   from pg_constraint k
   join tenant_tables t on t.oid = k.conrelid
   join pg_class f on f.oid = k.confrelid
   where k.contype = 'f' and f.relnamespace = 'doctor'::regnamespace and f.relname <> 'tenants'
     and exists (select 1 from pg_attribute a where a.attrelid = f.oid and a.attname = 'tenant_id')
     and not exists (select 1 from pg_attribute a
                     where a.attrelid = k.conrelid and a.attname = 'tenant_id'
                       and a.attnum = any(k.conkey))),
  null, 'FK para tabela de tenant é sempre composta com tenant_id'
);

select is(
  (select array_agg(relname order by relname) from tenant_tables t
   where has_table_privilege('authenticated', t.oid, 'select')
     and not exists (select 1 from pg_policy p where p.polrelid = t.oid)),
  null, 'tabela legível por authenticated tem política de RLS'
);

select is(
  (select array_agg(c.relname order by c.relname) from pg_class c
   where c.relnamespace = 'doctor'::regnamespace and c.relispartition
     and (has_table_privilege('authenticated', c.oid, 'select')
          or has_table_privilege('anon', c.oid, 'select'))),
  null, 'partições não são acessíveis direto (só pela tabela-mãe, com RLS)'
);

select is(
  (select array_agg(relname order by relname) from tenant_tables t
   where has_table_privilege('anon', t.oid, 'select') or has_table_privilege('anon', t.oid, 'insert')
      or has_table_privilege('anon', t.oid, 'update') or has_table_privilege('anon', t.oid, 'delete')),
  null, 'anon não tem privilégio em tabela do Doctor'
);

select is(
  (select array_agg(p.proname::text order by p.proname) from pg_proc p
   where p.pronamespace = 'doctor'::regnamespace and p.prosecdef
     and (p.proconfig is null
          or not exists (select 1 from unnest(p.proconfig) x where x like 'search_path=%')
          or p.proacl is null
          or exists (select 1 from aclexplode(p.proacl) e
                     where e.grantee = 0 and e.privilege_type = 'EXECUTE'))),
  null, 'security definer: search_path fixo e sem execute para public'
);

-- O token de ingestão é a única porta anônima: as duas funções resolvem o tenant pelo hash.
select is(
  (select array_agg(p.proname::text order by p.proname) from pg_proc p
   where p.pronamespace = 'doctor'::regnamespace and has_function_privilege('anon', p.oid, 'execute')),
  array['accept_ingestion_batch', 'resolve_ingestion_token'],
  'anon só executa as funções da ingestão por token'
);

-- O inventário pega a tabela nova fora do padrão (é o que bloqueia o merge).
create table doctor.zz_tabela_fora_do_padrao (id uuid primary key, integration_id uuid);
insert into tenant_tables select oid, relname from pg_class where oid = 'doctor.zz_tabela_fora_do_padrao'::regclass;
select is(
  (select array_agg(relname order by relname) from tenant_tables t
   where t.relname not in (select relname from exceptions)
     and (not (select relrowsecurity from pg_class where oid = t.oid)
          or not exists (select 1 from pg_attribute a where a.attrelid = t.oid and a.attname = 'tenant_id'))),
  array['zz_tabela_fora_do_padrao']::name[],
  'tabela sem RLS e sem tenant_id é detectada'
);

select * from finish();
rollback;
