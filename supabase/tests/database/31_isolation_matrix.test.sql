-- Suíte de isolamento gerada por tabela (ticket #27). Para cada tabela de tenant, cada Papel da
-- Organização A (owner, admin, analyst, viewer) tenta ler, inserir, alterar e apagar linhas da
-- Organização B, e mover uma linha de A para B. Nada pode passar: o acesso é negado (42501) ou não
-- alcança nenhuma linha. A fixture põe dados de B em todas as tabelas, para a leitura valer.
begin;
\ir ../helpers/tenancy.psql

select tests.create_user('00000000-0000-4000-8000-0000000a0001', 'owner@acme.test');
select tests.create_user('00000000-0000-4000-8000-0000000a0002', 'admin@acme.test');
select tests.create_user('00000000-0000-4000-8000-0000000a0003', 'analyst@acme.test');
select tests.create_user('00000000-0000-4000-8000-0000000a0004', 'viewer@acme.test');
select tests.create_user('00000000-0000-4000-8000-0000000b0001', 'owner@varejo.test');
select tests.create_tenant('00000000-0000-4000-8000-00000000ac01', 'acme');
select tests.create_tenant('00000000-0000-4000-8000-00000000be01', 'varejo');
select tests.add_member('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000a0001', 'owner');
select tests.add_member('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000a0002', 'admin');
select tests.add_member('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000a0003', 'analyst');
select tests.add_member('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000a0004', 'viewer');
select tests.add_member('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000b0001', 'owner');

-- Dados de B em todas as tabelas de tenant (como postgres, sem RLS).
select doctor.ensure_event_partition('2026-11-02');
insert into doctor.user_active_tenant (user_id, tenant_id)
values ('00000000-0000-4000-8000-0000000b0001', '00000000-0000-4000-8000-00000000be01')
on conflict (user_id) do nothing;
insert into doctor.integrations (id, tenant_id, name, source_system, target_system, environment)
values ('00000000-0000-4000-8000-0000000001b1', '00000000-0000-4000-8000-00000000be01', 'Notas', 'sap', 'gcp', 'prd'),
       ('00000000-0000-4000-8000-0000000001a1', '00000000-0000-4000-8000-00000000ac01', 'Pedidos', 'salesforce', 'sap', 'prd');
insert into doctor.raw_log_objects (id, tenant_id, storage_path, sha256, size_bytes, source)
values ('00000000-0000-4000-8000-0000000002b1', '00000000-0000-4000-8000-00000000be01',
  '00000000-0000-4000-8000-00000000be01/api/lote.json', repeat('a', 64), 10, 'api');
insert into doctor.imports (id, tenant_id, integration_id, filename, size_bytes, sha256)
values ('00000000-0000-4000-8000-0000000003b1', '00000000-0000-4000-8000-00000000be01',
  '00000000-0000-4000-8000-0000000001b1', 'logs.ndjson', 10, repeat('b', 64));
insert into doctor.import_rejections (tenant_id, import_id, line_number, reason)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000003b1', 1, 'JSON inválido');
insert into doctor.executions (id, tenant_id, integration_id, first_event_at, last_event_at)
values ('00000000-0000-4000-8000-0000000004b1', '00000000-0000-4000-8000-00000000be01',
  '00000000-0000-4000-8000-0000000001b1', '2026-11-02T14:00:00Z', '2026-11-02T14:00:30Z'),
       ('00000000-0000-4000-8000-0000000004b2', '00000000-0000-4000-8000-00000000be01',
  '00000000-0000-4000-8000-0000000001b1', '2026-11-02T14:00:00Z', '2026-11-02T14:00:30Z');
insert into doctor.execution_merges (tenant_id, survivor_id, merged_id)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000004b1',
  '00000000-0000-4000-8000-0000000004b2');
insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version, source, operation,
  severity, dedup_key, execution_ref)
values ('00000000-0000-4000-8000-0000000007b1', '00000000-0000-4000-8000-00000000be01',
  '00000000-0000-4000-8000-0000000001b1', '2026-11-02T14:00:10Z', '1.0', '{"provider": "sap"}',
  'BAPI', 'ERROR', 'dedup-b', '00000000-0000-4000-8000-0000000004b1');
insert into doctor.execution_stats_hourly (tenant_id, integration_id, hour)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000001b1', '2026-11-02T14:00:00Z')
on conflict do nothing;
insert into doctor.execution_stats_dirty (tenant_id, integration_id, hour)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000001b1', '2026-11-02T15:00:00Z')
on conflict do nothing;
insert into doctor.rule_matches (id, tenant_id, execution_id, rule_code, rule_version, matched_event_ids)
values ('00000000-0000-4000-8000-0000000006b1', '00000000-0000-4000-8000-00000000be01',
  '00000000-0000-4000-8000-0000000004b1', 'INT-003', '2026.10.1', array['00000000-0000-4000-8000-0000000007b1'::uuid]);
insert into doctor.incidents (id, tenant_id, integration_id, title, category, severity, rule_code,
  rule_version, first_seen_at, last_seen_at, execution_count)
values ('00000000-0000-4000-8000-0000000005b1', '00000000-0000-4000-8000-00000000be01',
  '00000000-0000-4000-8000-0000000001b1', 'Timeout', 'TIMEOUT', 'high', 'INT-003', '2026.10.1', now(), now(), 1);
insert into doctor.incident_executions (tenant_id, incident_id, execution_id)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000005b1',
  '00000000-0000-4000-8000-0000000004b1');
insert into doctor.incident_comments (tenant_id, incident_id, body_md)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000005b1', 'Olhando.');
insert into doctor.incident_history (tenant_id, incident_id, action)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000005b1', 'status');
insert into doctor.diagnoses (id, tenant_id, incident_id, version, status, stage, requested_mode, mode, processing_key)
values ('00000000-0000-4000-8000-0000000009b1', '00000000-0000-4000-8000-00000000be01',
  '00000000-0000-4000-8000-0000000005b1', 1, 'running', 'verification', 'hybrid', 'hybrid', 'k-b');
insert into doctor.diagnosis_hypotheses (tenant_id, diagnosis_id, rank, statement)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000009b1', 1, 'Gateway lento.');
insert into doctor.diagnosis_recommendations (tenant_id, diagnosis_id, rank, text, kind)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000009b1', 1, 'Confira o SAP.', 'verify');
insert into doctor.diagnosis_evidence (tenant_id, diagnosis_id, rank, kind, rule_match_id, label, finding)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000009b1', 1, 'rule_match',
  '00000000-0000-4000-8000-0000000006b1', 'INT-003', '504');
update doctor.diagnoses set status = 'published', stage = 'done', published_at = now()
where id = '00000000-0000-4000-8000-0000000009b1';
insert into doctor.diagnosis_feedback (tenant_id, diagnosis_id, verdict)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000009b1', 'accepted');
insert into doctor.knowledge_documents (id, tenant_id, title, source, storage_path, content_type, size_bytes, status)
values ('00000000-0000-4000-8000-0000000008b1', '00000000-0000-4000-8000-00000000be01', 'Runbook', 'upload',
  '00000000-0000-4000-8000-00000000be01/x/document.md', 'text/markdown', 10, 'ready');
insert into doctor.knowledge_chunks (tenant_id, document_id, ordinal, content, tokens)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000008b1', 0, 'VL10', 2);
insert into doctor.connectors (id, tenant_id, integration_id, provider, name)
values ('00000000-0000-4000-8000-000000000cb1', '00000000-0000-4000-8000-00000000be01',
  '00000000-0000-4000-8000-0000000001b1', 'gcp', 'Cloud Logging');
insert into doctor.connector_syncs (tenant_id, connector_id)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-000000000cb1');
insert into doctor.ingestion_tokens (tenant_id, name, integration_id, token_hash, prefix)
values ('00000000-0000-4000-8000-00000000be01', 'Token B', '00000000-0000-4000-8000-0000000001b1',
  repeat('c', 64), 'aid_test');
insert into doctor.ingestion_batches (tenant_id, integration_id, connector_id, events, event_count)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000001b1',
  '00000000-0000-4000-8000-000000000cb1', '[]', 0);
insert into doctor.idempotency_keys (tenant_id, user_id, key, request_hash)
values ('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000b0001', 'chave-b', repeat('d', 64));
insert into doctor.invitations (tenant_id, email, role, token_hash, invited_by)
values ('00000000-0000-4000-8000-00000000be01', 'novo@varejo.test', 'viewer', repeat('e', 64),
  '00000000-0000-4000-8000-0000000b0001');
insert into doctor.outbox_messages (tenant_id, topic, payload)
values ('00000000-0000-4000-8000-00000000be01', 'rules.evaluate', '{}');
insert into doctor.audit_logs (tenant_id, actor_type, action)
values ('00000000-0000-4000-8000-00000000be01', 'system', 'teste.isolamento');

-- Tabelas de tenant: todas com tenant_id, menos o catálogo e o controle (inventário no teste 30).
create temporary table matrix_tables as
select c.relname::text as name
from pg_class c
where c.relnamespace = 'doctor'::regnamespace and c.relkind in ('r', 'p') and not c.relispartition
  and exists (select 1 from pg_attribute a where a.attrelid = c.oid and a.attname = 'tenant_id' and not a.attisdropped);

create temporary table matrix_roles (user_id uuid, role text, aal text);
insert into matrix_roles values
  ('00000000-0000-4000-8000-0000000a0001', 'owner', 'aal2'),
  ('00000000-0000-4000-8000-0000000a0002', 'admin', 'aal2'),
  ('00000000-0000-4000-8000-0000000a0003', 'analyst', 'aal1'),
  ('00000000-0000-4000-8000-0000000a0004', 'viewer', 'aal1');

grant select on matrix_tables, matrix_roles to authenticated;

-- Sonda: roda o comando com o papel atual e diz o que aconteceu, sem deixar efeito.
create function pg_temp.probe(command text) returns text language plpgsql as $$
declare
  affected bigint;
begin
  begin
    execute command;
    get diagnostics affected = row_count;
    raise exception using errcode = 'XX999', message = affected::text;
  exception
    when insufficient_privilege then return 'denied';
    when sqlstate 'XX999' then return 'rows:' || sqlerrm;
    when others then return 'error:' || sqlstate;
  end;
end;
$$;

create function pg_temp.visible(tbl text) returns text language plpgsql as $$
declare
  found bigint;
begin
  execute format('select count(*) from doctor.%I where tenant_id = %L', tbl, '00000000-0000-4000-8000-00000000be01')
    into found;
  return 'rows:' || found;
exception
  when insufficient_privilege then return 'denied';
end;
$$;

select plan((select count(*)::int * 4 * 5 + 1 from matrix_tables));

select is(
  (select array_agg(name order by name) from matrix_tables where pg_temp.visible(name) = 'rows:0'),
  null, 'a fixture põe dados de B em todas as tabelas de tenant'
);

create temporary table matrix_results (role text, tbl text, operation text, outcome text);
grant insert on matrix_results to authenticated;

do $$
declare
  r record;
  t record;
begin
  for r in select * from matrix_roles loop
    perform tests.authenticate_as(r.user_id, '00000000-0000-4000-8000-00000000ac01', r.role, r.aal);
    for t in select name from matrix_tables order by name loop
      insert into matrix_results values
        (r.role, t.name, 'select', pg_temp.visible(t.name)),
        (r.role, t.name, 'insert', pg_temp.probe(format(
          'insert into doctor.%I (tenant_id) values (%L)', t.name, '00000000-0000-4000-8000-00000000be01'))),
        (r.role, t.name, 'update', pg_temp.probe(format(
          'update doctor.%I set tenant_id = tenant_id where tenant_id = %L', t.name,
          '00000000-0000-4000-8000-00000000be01'))),
        (r.role, t.name, 'delete', pg_temp.probe(format(
          'delete from doctor.%I where tenant_id = %L', t.name, '00000000-0000-4000-8000-00000000be01'))),
        (r.role, t.name, 'transfer', pg_temp.probe(format(
          'update doctor.%I set tenant_id = %L where tenant_id = %L', t.name,
          '00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-00000000ac01')));
    end loop;
    perform tests.clear_authentication();
  end loop;
end;
$$;

select ok(
  outcome in ('denied', 'rows:0'),
  format('%s não alcança %s de outra Organização (%s): %s', role, tbl, operation, outcome)
)
from matrix_results order by tbl, operation, role;

select * from finish();
rollback;
