-- Ticket #7: respostas gravadas por `Idempotency-Key`. A limpeza é preguiçosa, na própria API: um job
-- no pg_cron do projeto compartilhado afetaria o agendador do jayv-coder.
create table doctor.idempotency_keys (
  tenant_id uuid not null references doctor.tenants (id) on delete cascade,
  key text not null check (char_length(key) between 1 and 255),
  request_hash text not null,
  response_status integer,
  response_body text,
  created_at timestamptz not null default now(),
  primary key (tenant_id, key)
);
comment on table doctor.idempotency_keys is 'Resposta de escritas repetidas com a mesma chave, por 24 h.';

alter table doctor.idempotency_keys enable row level security;

revoke all on doctor.idempotency_keys from anon, authenticated;
grant select, insert, update, delete on doctor.idempotency_keys to authenticated;

create policy idempotency_keys_own_tenant on doctor.idempotency_keys
for all to authenticated
using (tenant_id = (select doctor.current_tenant_id()))
with check (tenant_id = (select doctor.current_tenant_id()));
