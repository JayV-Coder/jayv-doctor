begin;
\ir ../helpers/tenancy.psql
select plan(13);

select tests.create_user('00000000-0000-4000-8000-0000000a0001', 'owner@acme.test');
select tests.create_tenant('00000000-0000-4000-8000-00000000ac01', 'acme');
select tests.create_tenant('00000000-0000-4000-8000-00000000be01', 'varejo');
select tests.add_member('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000a0001', 'owner');
insert into doctor.integrations (id, tenant_id, name, source_system, target_system, environment)
values ('00000000-0000-4000-8000-0000000001a1', '00000000-0000-4000-8000-00000000ac01', 'Pedidos', 'salesforce', 'sap', 'prd');
select doctor.ensure_event_partition(now()::date);

-- Eventos gravados contam no mês, só os que entraram de fato.
insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version, source, operation, severity, dedup_key)
select gen_random_uuid(), '00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000001a1',
  now(), '1.0', '{}', 'BAPI', 'INFO', 'evento-' || n
from generate_series(1, 3) n;
insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version, source, operation, severity, dedup_key)
values (gen_random_uuid(), '00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000001a1',
  now(), '1.0', '{}', 'BAPI', 'INFO', 'evento-1')
on conflict do nothing;
select is(doctor.current_usage('00000000-0000-4000-8000-00000000ac01', 'events_ingested'), 3::bigint,
  'conta os 3 Eventos gravados (o repetido descartado não entra)');

-- Avisos de 80% e 100%, uma vez cada.
select is(doctor.increment_usage('00000000-0000-4000-8000-00000000ac01', 'diagnoses_llm', 799), 799::bigint, 'incremento atômico');
select is(doctor.increment_usage('00000000-0000-4000-8000-00000000ac01', 'diagnoses_llm', 1), 800::bigint, '80% da Cota de IA');
select doctor.increment_usage('00000000-0000-4000-8000-00000000ac01', 'diagnoses_llm', 1);
select results_eq(
  $$select payload ->> 'resource', (payload ->> 'threshold')::int from doctor.outbox_messages
    where tenant_id = '00000000-0000-4000-8000-00000000ac01' and topic = 'usage.threshold'$$,
  $$values ('diagnoses_llm'::text, 80)$$,
  'aviso de 80% sai uma vez'
);
select is(doctor.llm_quota_available('00000000-0000-4000-8000-00000000ac01'), true, 'ainda há Cota de IA');
select doctor.increment_usage('00000000-0000-4000-8000-00000000ac01', 'diagnoses_llm', 199);
select is(doctor.llm_quota_available('00000000-0000-4000-8000-00000000ac01'), false,
  '1.000 de 1.000: o próximo Diagnóstico roda só com as Regras');
select is(
  (select count(*)::int from doctor.usage_alerts where tenant_id = '00000000-0000-4000-8000-00000000ac01'),
  2, 'avisos de 80% e 100%'
);

-- Ingestão acima de 110%: o lote é recusado; a Importação também.
select doctor.increment_usage('00000000-0000-4000-8000-00000000ac01', 'events_ingested', 3300000);
select throws_ok(
  $$insert into doctor.ingestion_batches (tenant_id, integration_id, connector_id, events, event_count)
    values ('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000001a1', null, '[]', 20)$$,
  'DR050', null, 'lote acima de 110% da Cota de Eventos é recusado'
);
select throws_ok(
  $$insert into doctor.imports (tenant_id, integration_id, filename, size_bytes, sha256)
    values ('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000001a1', 'a.ndjson', 10, repeat('a', 64))$$,
  'DR050', null, 'e a Importação também'
);

-- Conectores e membros no limite do plano piloto (5 e 20).
insert into doctor.connectors (tenant_id, integration_id, provider, name)
select '00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000001a1', 'gcp', 'Conector ' || n
from generate_series(1, 5) n;
select throws_ok(
  $$insert into doctor.connectors (tenant_id, integration_id, provider, name)
    values ('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000001a1', 'gcp', 'Sexto')$$,
  'DR051', null, 'sexto Conector bloqueado no piloto'
);
insert into doctor.invitations (tenant_id, email, role, token_hash, invited_by)
select '00000000-0000-4000-8000-00000000ac01', 'pessoa' || n || '@acme.test', 'viewer', md5(n::text) || md5(n::text),
  '00000000-0000-4000-8000-0000000a0001'
from generate_series(1, 19) n;
select throws_ok(
  $$insert into doctor.invitations (tenant_id, email, role, token_hash, invited_by)
    values ('00000000-0000-4000-8000-00000000ac01', 'mais@acme.test', 'viewer', repeat('f', 64),
      '00000000-0000-4000-8000-0000000a0001')$$,
  'DR051', null, 'convite além de 20 membros (contando os pendentes) bloqueado'
);

-- Tela 17: o uso da Organização ativa, com o limite.
select tests.authenticate_as('00000000-0000-4000-8000-0000000a0001', '00000000-0000-4000-8000-00000000ac01', 'owner');
select results_eq(
  $$select resource, used, quota from doctor.my_usage() where resource in ('diagnoses_llm', 'connectors_active')$$,
  $$values ('diagnoses_llm'::text, 1000::bigint, 1000::bigint), ('connectors_active'::text, 5::bigint, 5::bigint)$$,
  'uso e limite da Organização ativa'
);
select is((select count(*)::int from doctor.usage_records where tenant_id <> '00000000-0000-4000-8000-00000000ac01'), 0,
  'o consumo de outra Organização não aparece');
select tests.clear_authentication();

select * from finish();
rollback;
