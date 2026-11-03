-- Dashboard executivo (ticket #21): agregado por hora das Execuções e baseline do MTTR.

alter table doctor.tenants add column mttr_baseline_minutes integer
  check (mttr_baseline_minutes is null or mttr_baseline_minutes > 0);
comment on column doctor.tenants.mttr_baseline_minutes is
  'MTTR de referência do piloto, em minutos: o Dashboard mostra a variação contra ele.';

create table doctor.execution_stats_hourly (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references doctor.tenants (id) on delete cascade,
  integration_id uuid not null,
  hour timestamptz not null check (date_trunc('hour', hour) = hour),
  total integer not null default 0 check (total >= 0),
  failed integer not null default 0 check (failed >= 0 and failed <= total),
  -- Falhas por categoria do Incidente da Execução; sem Incidente, `UNCLASSIFIED`.
  by_category jsonb not null default '{}' check (jsonb_typeof(by_category) = 'object'),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, integration_id, hour),
  foreign key (tenant_id, integration_id) references doctor.integrations (tenant_id, id) on delete cascade
);
comment on table doctor.execution_stats_hourly is 'Execuções e falhas por Integração e hora (pelo primeiro Evento).';
create index execution_stats_hourly_time_idx on doctor.execution_stats_hourly (tenant_id, hour desc);

create trigger execution_stats_hourly_set_updated_at
before update on doctor.execution_stats_hourly
for each row execute function doctor.set_updated_at();

alter table doctor.execution_stats_hourly enable row level security;
revoke all on doctor.execution_stats_hourly from anon, authenticated;
grant select on doctor.execution_stats_hourly to authenticated;
create policy execution_stats_hourly_select on doctor.execution_stats_hourly
for select to authenticated
using (tenant_id = (select doctor.current_tenant_id()));

-- Para achar o que mudou desde a última rodada (job de plataforma, por isso sem tenant_id na
-- frente).
create index executions_updated_idx on doctor.executions (updated_at);
create index incident_executions_updated_idx on doctor.incident_executions (updated_at);

-- Recalcula, do zero, as horas tocadas por Execuções alteradas desde `since` (todas as
-- Organizações: job de plataforma). Recalcular a hora inteira, em vez de somar deltas, deixa a
-- rodada idempotente: repetir não conta duas vezes, e fusões e reaberturas se acertam sozinhas.
create function doctor.refresh_execution_stats(since timestamptz)
returns integer
language sql
set search_path = ''
as $$
  with touched as (
    select tenant_id, integration_id, date_trunc('hour', first_event_at) as hour
    from doctor.executions
    where updated_at >= since
    -- A categoria chega depois do fechamento, quando a Regra põe a Execução num Incidente.
    union
    select x.tenant_id, x.integration_id, date_trunc('hour', x.first_event_at)
    from doctor.incident_executions ie
    join doctor.executions x on x.tenant_id = ie.tenant_id and x.id = ie.execution_id
    where ie.updated_at >= since
  ),
  categorized as (
    select x.tenant_id, x.integration_id, date_trunc('hour', x.first_event_at) as hour,
      x.status, coalesce(inc.category, 'UNCLASSIFIED') as category
    from touched t
    join doctor.executions x
      on x.tenant_id = t.tenant_id and x.integration_id = t.integration_id
      and x.first_event_at >= t.hour and x.first_event_at < t.hour + interval '1 hour'
    left join doctor.incident_executions ie on ie.tenant_id = x.tenant_id and ie.execution_id = x.id
    left join doctor.incidents inc on inc.tenant_id = ie.tenant_id and inc.id = ie.incident_id
    where x.merged_into is null
  ),
  hourly as (
    select t.tenant_id, t.integration_id, t.hour,
      count(c.status)::int as total,
      (count(*) filter (where c.status = 'failed'))::int as failed,
      coalesce(
        (select jsonb_object_agg(category, n) from (
          select c2.category, count(*) as n from categorized c2
          where c2.tenant_id = t.tenant_id and c2.integration_id = t.integration_id
            and c2.hour = t.hour and c2.status = 'failed'
          group by c2.category
        ) per_category),
        '{}'
      ) as by_category
    from touched t
    left join categorized c
      on c.tenant_id = t.tenant_id and c.integration_id = t.integration_id and c.hour = t.hour
    group by t.tenant_id, t.integration_id, t.hour
  ),
  upserted as (
    insert into doctor.execution_stats_hourly (tenant_id, integration_id, hour, total, failed, by_category)
    select tenant_id, integration_id, hour, total, failed, by_category from hourly
    on conflict (tenant_id, integration_id, hour) do update
      set total = excluded.total, failed = excluded.failed, by_category = excluded.by_category
    returning 1
  )
  select count(*)::int from upserted
$$;

revoke all on function doctor.refresh_execution_stats(timestamptz) from public, anon, authenticated;
grant execute on function doctor.refresh_execution_stats(timestamptz) to service_role;
