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

-- Dados de A e de B em todas as tabelas de tenant (como postgres, sem RLS): a leitura de B e a
-- transferência de uma linha de A para B precisam de linha dos dois lados.
select doctor.ensure_event_partition('2026-11-02');

create function pg_temp.seed(t uuid, owner uuid) returns void language plpgsql as $$
declare
  integration uuid := gen_random_uuid();
  raw_log uuid := gen_random_uuid();
  import uuid := gen_random_uuid();
  execution uuid := gen_random_uuid();
  merged uuid := gen_random_uuid();
  event uuid := gen_random_uuid();
  match uuid := gen_random_uuid();
  incident uuid := gen_random_uuid();
  diagnosis uuid := gen_random_uuid();
  document uuid := gen_random_uuid();
  connector uuid := gen_random_uuid();
begin
  insert into doctor.user_active_tenant (user_id, tenant_id) values (owner, t)
  on conflict (user_id) do nothing;
  insert into doctor.integrations (id, tenant_id, name, source_system, target_system, environment)
  values (integration, t, 'Notas', 'sap', 'gcp', 'prd');
  insert into doctor.raw_log_objects (id, tenant_id, storage_path, sha256, size_bytes, source)
  values (raw_log, t, t::text || '/api/lote.json', repeat('a', 64), 10, 'api');
  insert into doctor.imports (id, tenant_id, integration_id, filename, size_bytes, sha256)
  values (import, t, integration, 'logs.ndjson', 10, repeat('b', 64));
  insert into doctor.import_rejections (tenant_id, import_id, line_number, reason)
  values (t, import, 1, 'JSON inválido');
  insert into doctor.executions (id, tenant_id, integration_id, first_event_at, last_event_at)
  values (execution, t, integration, '2026-11-02T14:00:00Z', '2026-11-02T14:00:30Z'),
         (merged, t, integration, '2026-11-02T14:00:00Z', '2026-11-02T14:00:30Z');
  insert into doctor.execution_merges (tenant_id, survivor_id, merged_id) values (t, execution, merged);
  insert into doctor.events (id, tenant_id, integration_id, timestamp, schema_version, source, operation,
    severity, dedup_key, execution_ref)
  values (event, t, integration, '2026-11-02T14:00:10Z', '1.0', '{"provider": "sap"}', 'BAPI', 'ERROR',
    'dedup-' || t::text, execution);
  insert into doctor.execution_stats_hourly (tenant_id, integration_id, hour)
  values (t, integration, '2026-11-02T14:00:00Z') on conflict do nothing;
  insert into doctor.execution_stats_dirty (tenant_id, integration_id, hour)
  values (t, integration, '2026-11-02T15:00:00Z') on conflict do nothing;
  insert into doctor.rule_matches (id, tenant_id, execution_id, rule_code, rule_version, matched_event_ids)
  values (match, t, execution, 'INT-003', '2026.10.1', array[event]);
  insert into doctor.incidents (id, tenant_id, integration_id, title, category, severity, rule_code,
    rule_version, first_seen_at, last_seen_at, execution_count)
  values (incident, t, integration, 'Timeout', 'TIMEOUT', 'high', 'INT-003', '2026.10.1', now(), now(), 1);
  insert into doctor.incident_executions (tenant_id, incident_id, execution_id) values (t, incident, execution);
  insert into doctor.incident_comments (tenant_id, incident_id, body_md) values (t, incident, 'Olhando.');
  insert into doctor.incident_history (tenant_id, incident_id, action) values (t, incident, 'status');
  insert into doctor.diagnoses (id, tenant_id, incident_id, version, status, stage, requested_mode, mode,
    processing_key)
  values (diagnosis, t, incident, 1, 'running', 'verification', 'hybrid', 'hybrid', 'k-' || t::text);
  insert into doctor.diagnosis_hypotheses (tenant_id, diagnosis_id, rank, statement)
  values (t, diagnosis, 1, 'Gateway lento.');
  insert into doctor.diagnosis_recommendations (tenant_id, diagnosis_id, rank, text, kind)
  values (t, diagnosis, 1, 'Confira o SAP.', 'verify');
  insert into doctor.diagnosis_evidence (tenant_id, diagnosis_id, rank, kind, rule_match_id, label, finding)
  values (t, diagnosis, 1, 'rule_match', match, 'INT-003', '504');
  update doctor.diagnoses set status = 'published', stage = 'done', published_at = now() where id = diagnosis;
  insert into doctor.diagnosis_feedback (tenant_id, diagnosis_id, verdict) values (t, diagnosis, 'accepted');
  insert into doctor.knowledge_documents (id, tenant_id, title, source, storage_path, content_type,
    size_bytes, status)
  values (document, t, 'Runbook', 'upload', t::text || '/x/document.md', 'text/markdown', 10, 'ready');
  insert into doctor.knowledge_chunks (tenant_id, document_id, ordinal, content, tokens)
  values (t, document, 0, 'VL10', 2);
  insert into doctor.connectors (id, tenant_id, integration_id, provider, name)
  values (connector, t, integration, 'gcp', 'Cloud Logging');
  insert into doctor.connector_syncs (tenant_id, connector_id) values (t, connector);
  insert into doctor.ingestion_tokens (tenant_id, name, integration_id, token_hash, prefix)
  values (t, 'Token', integration, md5(t::text) || md5(t::text), 'aid_test');
  insert into doctor.ingestion_batches (tenant_id, integration_id, connector_id, events, event_count)
  values (t, integration, connector, '[]', 0);
  insert into doctor.idempotency_keys (tenant_id, user_id, key, request_hash)
  values (t, owner, 'chave-' || t::text, repeat('d', 64));
  insert into doctor.invitations (tenant_id, email, role, token_hash, invited_by)
  values (t, 'novo-' || t::text || '@exemplo.test', 'viewer', md5(t::text || 'convite') || md5(t::text), owner);
  insert into doctor.outbox_messages (tenant_id, topic, payload) values (t, 'rules.evaluate', '{}');
  insert into doctor.audit_logs (tenant_id, actor_type, action) values (t, 'system', 'teste.isolamento');
  insert into doctor.retention_policies (tenant_id, data_class, days) values (t, 'raw_logs', 15);
  insert into doctor.deletion_receipts (tenant_id, requested_at) values (t, now());
  insert into doctor.usage_records (tenant_id, resource, period_start, quantity)
  values (t, 'diagnoses_llm', date_trunc('month', now())::date, 1)
  on conflict (tenant_id, resource, period_start) do nothing;
  insert into doctor.usage_llm (tenant_id, diagnosis_id, provider) values (t, diagnosis, 'fake');
  insert into doctor.usage_alerts (tenant_id, resource, period_start, threshold)
  values (t, 'diagnoses_llm', date_trunc('month', now())::date, 80);
end;
$$;

select pg_temp.seed('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000a0001');
select pg_temp.seed('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000b0001');

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

create function pg_temp.visible(tbl text, tenant uuid default '00000000-0000-4000-8000-00000000be01')
returns text language plpgsql as $$
declare
  found bigint;
begin
  execute format('select count(*) from doctor.%I where tenant_id = %L', tbl, tenant)
    into found;
  return 'rows:' || found;
exception
  when insufficient_privilege then return 'denied';
end;
$$;

select plan((select count(*)::int * 4 * 5 + 2 from matrix_tables));

select is(
  (select array_agg(name order by name) from matrix_tables where pg_temp.visible(name) = 'rows:0'),
  null, 'a fixture põe dados de B em todas as tabelas de tenant'
);
select is(
  (select array_agg(name order by name) from matrix_tables
   where pg_temp.visible(name, '00000000-0000-4000-8000-00000000ac01') = 'rows:0'),
  null, 'e de A também: a transferência de A para B tem linha para tentar mover'
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
