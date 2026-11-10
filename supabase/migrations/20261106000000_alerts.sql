-- Ticket #41: Regras de alerta e notificações (push no PWA, e-mail, Slack e Microsoft Teams).
-- O worker `notifier` (ADR-0017) consome `alert.evaluate`, que nasce aqui por trigger: na
-- outbox (Incidente aberto ou atualizado, Diagnóstico publicado) e na mudança de um Conector
-- para `failing`. Taxa de erro e Diagnóstico aguardando revisão saem da varredura agendada.
-- As mensagens levam só título, severidade, Integração e o link: nada de log ou de Evidência.

-- Canais da Organização. O endereço do Slack e do Teams é um segredo (quem tem o webhook posta no
-- canal): vai para o Vault, como a credencial dos Conectores, e só o `notifier` o lê.
create table doctor.notification_channels (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references doctor.tenants (id) on delete cascade,
  type text not null check (type in ('email', 'slack', 'teams', 'webpush')),
  name text not null check (char_length(btrim(name)) between 2 and 80),
  -- email e webpush: `{"audience": "managers" | "all"}`, sempre Usuários da Organização.
  config jsonb not null default '{}' check (jsonb_typeof(config) = 'object'),
  secret_id uuid,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, name),
  check ((type in ('slack', 'teams')) = (secret_id is not null))
);
comment on table doctor.notification_channels is 'Canal de notificação da Organização (e-mail, Slack, Teams, push).';

create trigger notification_channels_set_updated_at
before update on doctor.notification_channels
for each row execute function doctor.set_updated_at();

alter table doctor.notification_channels enable row level security;
revoke all on doctor.notification_channels from anon, authenticated;
-- Sem `secret_id`: nem o id do segredo chega ao cliente.
grant select (id, tenant_id, type, name, config, created_by, created_at, updated_at)
  on doctor.notification_channels to authenticated;
create policy notification_channels_select on doctor.notification_channels
for select to authenticated
using (tenant_id = (select doctor.current_tenant_id()));

-- Regras de alerta. `conditions`: `{"type": "incident", "min_severity", "environments",
-- "integrations"}`, `{"type": "error_rate", "threshold_pct", "minutes", "integrations"}`,
-- `{"type": "connector_failing"}` ou `{"type": "diagnosis_review", "minutes"}`, validadas pela API.
create table doctor.alert_rules (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null default doctor.current_tenant_id() references doctor.tenants (id) on delete cascade,
  name text not null check (char_length(btrim(name)) between 2 and 80),
  enabled boolean not null default true,
  conditions jsonb not null check (jsonb_typeof(conditions) = 'object' and conditions ? 'type'),
  -- Ids de canais desta Organização (conferidos pela API e de novo pelo `notifier`).
  channels jsonb not null default '[]' check (jsonb_typeof(channels) = 'array'),
  -- `{"start": "22:00", "end": "07:00", "timezone": "America/Sao_Paulo"}`; crítico ignora.
  quiet_hours jsonb check (quiet_hours is null or jsonb_typeof(quiet_hours) = 'object'),
  created_by uuid default auth.uid() references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, name)
);
comment on table doctor.alert_rules is 'Regra de alerta: condição, canais e horário de silêncio.';
create index alert_rules_enabled_idx on doctor.alert_rules (tenant_id) where enabled;

create trigger alert_rules_set_updated_at
before update on doctor.alert_rules
for each row execute function doctor.set_updated_at();

alter table doctor.alert_rules enable row level security;
revoke all on doctor.alert_rules from anon, authenticated;
grant select, delete on doctor.alert_rules to authenticated;
grant insert (name, enabled, conditions, channels, quiet_hours) on doctor.alert_rules to authenticated;
grant update (name, enabled, conditions, channels, quiet_hours) on doctor.alert_rules to authenticated;
create policy alert_rules_select on doctor.alert_rules
for select to authenticated
using (tenant_id = (select doctor.current_tenant_id()));
create policy alert_rules_insert on doctor.alert_rules
for insert to authenticated
with check (tenant_id = (select doctor.current_tenant_id()) and (select doctor.is_manager()));
create policy alert_rules_update on doctor.alert_rules
for update to authenticated
using (tenant_id = (select doctor.current_tenant_id()) and (select doctor.is_manager()))
with check (tenant_id = (select doctor.current_tenant_id()) and (select doctor.is_manager()));
create policy alert_rules_delete on doctor.alert_rules
for delete to authenticated
using (tenant_id = (select doctor.current_tenant_id()) and (select doctor.is_manager()));

-- Push no PWA: uma assinatura por aparelho do Usuário, nesta Organização. Cada um vê e apaga
-- só as suas.
create table doctor.push_subscriptions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null default doctor.current_tenant_id() references doctor.tenants (id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  endpoint text not null check (endpoint ~ '^https://' and char_length(endpoint) <= 1000),
  p256dh text not null check (char_length(p256dh) between 40 and 200),
  auth text not null check (char_length(auth) between 10 and 100),
  user_agent text check (char_length(user_agent) <= 300),
  last_success_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, user_id, endpoint)
);
comment on table doctor.push_subscriptions is 'Assinatura de Web Push de um aparelho do Usuário.';

create trigger push_subscriptions_set_updated_at
before update on doctor.push_subscriptions
for each row execute function doctor.set_updated_at();

alter table doctor.push_subscriptions enable row level security;
revoke all on doctor.push_subscriptions from anon, authenticated;
grant select (id, tenant_id, user_id, endpoint, user_agent, last_success_at, created_at)
  on doctor.push_subscriptions to authenticated;
grant insert (endpoint, p256dh, auth, user_agent) on doctor.push_subscriptions to authenticated;
grant delete on doctor.push_subscriptions to authenticated;
create policy push_subscriptions_own on doctor.push_subscriptions
for all to authenticated
using (tenant_id = (select doctor.current_tenant_id()) and user_id = (select auth.uid()))
with check (
  tenant_id = (select doctor.current_tenant_id()) and user_id = (select auth.uid())
  and exists (select 1 from doctor.memberships m
    where m.tenant_id = push_subscriptions.tenant_id and m.user_id = (select auth.uid()))
);

-- Silêncio fora do plantão, por Usuário (push e e-mail para ele); crítico chega mesmo assim.
create table doctor.alert_preferences (
  tenant_id uuid not null default doctor.current_tenant_id() references doctor.tenants (id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users (id) on delete cascade,
  id uuid not null default gen_random_uuid(),
  quiet_hours jsonb check (quiet_hours is null or jsonb_typeof(quiet_hours) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (tenant_id, user_id),
  unique (tenant_id, id)
);
comment on table doctor.alert_preferences is 'Preferências de alerta do Usuário na Organização.';

create trigger alert_preferences_set_updated_at
before update on doctor.alert_preferences
for each row execute function doctor.set_updated_at();

alter table doctor.alert_preferences enable row level security;
revoke all on doctor.alert_preferences from anon, authenticated;
grant select on doctor.alert_preferences to authenticated;
grant insert (quiet_hours) on doctor.alert_preferences to authenticated;
grant update (quiet_hours) on doctor.alert_preferences to authenticated;
create policy alert_preferences_own on doctor.alert_preferences
for all to authenticated
using (tenant_id = (select doctor.current_tenant_id()) and user_id = (select auth.uid()))
with check (tenant_id = (select doctor.current_tenant_id()) and user_id = (select auth.uid()));

-- Entregas: histórico e base da deduplicação (uma notificação por assunto e Regra a cada 15 min).
create table doctor.notification_deliveries (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references doctor.tenants (id) on delete cascade,
  rule_id uuid,
  channel_id uuid,
  -- O que a notificação trata: `incident:<id>`, `connector:<id>`, `error_rate:<integração>` etc.
  subject text not null check (char_length(subject) between 1 and 200),
  status text not null check (status in ('sent', 'failed', 'suppressed', 'quiet')),
  error text check (char_length(error) <= 500),
  created_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, rule_id) references doctor.alert_rules (tenant_id, id) on delete set null (rule_id),
  foreign key (tenant_id, channel_id) references doctor.notification_channels (tenant_id, id)
    on delete set null (channel_id)
);
comment on table doctor.notification_deliveries is 'Entrega de notificação por canal, com o motivo de não ter saído.';
create index notification_deliveries_dedup_idx
  on doctor.notification_deliveries (tenant_id, rule_id, subject, created_at desc);

alter table doctor.notification_deliveries enable row level security;
revoke all on doctor.notification_deliveries from anon, authenticated;
grant select on doctor.notification_deliveries to authenticated;
create policy notification_deliveries_select on doctor.notification_deliveries
for select to authenticated
using (tenant_id = (select doctor.current_tenant_id()) and (select doctor.is_manager()));

-- Canais com segredo: Owner ou Admin com MFA cria; o webhook vai para o Vault na mesma transação.
create function doctor.create_notification_channel(type text, name text, config jsonb, secret text)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  tenant uuid := doctor.current_tenant_id();
  new_id uuid := gen_random_uuid();
begin
  perform doctor.require_manager();
  insert into doctor.notification_channels (id, tenant_id, type, name, config, secret_id, created_by)
  values (
    new_id, tenant, create_notification_channel.type, btrim(create_notification_channel.name),
    create_notification_channel.config,
    case when create_notification_channel.secret is null then null
      else vault.create_secret(create_notification_channel.secret, 'doctor/channel/' || new_id,
        'Webhook de canal de notificação do Doctor') end,
    auth.uid()
  );
  perform doctor.record_audit(tenant, 'notification_channel.create', new_id::text);
  return new_id;
end;
$$;

create function doctor.delete_notification_channel(target uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  tenant uuid := doctor.current_tenant_id();
  current_secret uuid;
begin
  perform doctor.require_manager();
  delete from doctor.notification_channels c where c.id = target and c.tenant_id = tenant
  returning c.secret_id into current_secret;
  if not found then
    raise no_data_found using message = 'Canal não encontrado';
  end if;
  if current_secret is not null then
    delete from vault.secrets s where s.id = current_secret;
  end if;
  perform doctor.record_audit(tenant, 'notification_channel.delete', target::text);
end;
$$;

-- Só a plataforma (worker `notifier`, service_role) lê o webhook.
create function doctor.get_channel_secret(target uuid)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  value text;
begin
  select s.decrypted_secret into value
  from doctor.notification_channels c join vault.decrypted_secrets s on s.id = c.secret_id
  where c.id = target;
  if value is null then
    raise no_data_found using message = 'Canal sem segredo';
  end if;
  return value;
end;
$$;

revoke all on function doctor.create_notification_channel(text, text, jsonb, text) from public, anon, service_role;
revoke all on function doctor.delete_notification_channel(uuid) from public, anon, service_role;
revoke all on function doctor.get_channel_secret(uuid) from public, anon, authenticated;
grant execute on function doctor.create_notification_channel(text, text, jsonb, text) to authenticated;
grant execute on function doctor.delete_notification_channel(uuid) to authenticated;
grant execute on function doctor.get_channel_secret(uuid) to service_role;

-- `alert.evaluate` nasce junto com o que pode notificar, na mesma transação.
create function doctor.queue_alert_from_outbox()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into doctor.outbox_messages (tenant_id, topic, payload)
  values (new.tenant_id, 'alert.evaluate', new.payload || jsonb_build_object('source', new.topic));
  return new;
end;
$$;
revoke all on function doctor.queue_alert_from_outbox() from public, anon, authenticated;
create trigger outbox_queue_alert
after insert on doctor.outbox_messages
for each row when (new.topic in ('incident.opened', 'incident.updated', 'diagnosis.published'))
execute function doctor.queue_alert_from_outbox();

create function doctor.queue_alert_from_connector()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into doctor.outbox_messages (tenant_id, topic, payload)
  values (new.tenant_id, 'alert.evaluate',
    jsonb_build_object('source', 'connector.failing', 'connector_id', new.id));
  return new;
end;
$$;
revoke all on function doctor.queue_alert_from_connector() from public, anon, authenticated;
create trigger connectors_queue_alert
after update of status on doctor.connectors
for each row when (new.status = 'failing' and old.status is distinct from 'failing')
execute function doctor.queue_alert_from_connector();

-- Público de um canal de e-mail ou push: Usuários da Organização (gestores ou todos), com o
-- e-mail e o silêncio de cada um. Só a plataforma (`notifier`) chama, como `quota_recipients`.
create function doctor.alert_audience(tenant uuid, everyone boolean)
returns table (user_id uuid, email text, quiet_hours jsonb)
language sql
stable
security definer
set search_path = ''
as $$
  select m.user_id, u.email::text, p.quiet_hours
  from doctor.memberships m
  join auth.users u on u.id = m.user_id
  left join doctor.alert_preferences p on p.tenant_id = m.tenant_id and p.user_id = m.user_id
  where m.tenant_id = alert_audience.tenant
    and (alert_audience.everyone or m.role in ('owner', 'admin'))
  order by m.user_id
$$;
revoke all on function doctor.alert_audience(uuid, boolean) from public, anon, authenticated;
grant execute on function doctor.alert_audience(uuid, boolean) to service_role;
