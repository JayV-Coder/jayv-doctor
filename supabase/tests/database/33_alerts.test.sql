begin;
\ir ../helpers/tenancy.psql
select plan(14);

select tests.create_user('00000000-0000-4000-8000-0000000d0001', 'admin@acme.test');
select tests.create_user('00000000-0000-4000-8000-0000000d0002', 'analyst@acme.test');
select tests.create_user('00000000-0000-4000-8000-0000000d0003', 'admin@varejo.test');
select tests.create_tenant('00000000-0000-4000-8000-00000000ac01', 'acme');
select tests.create_tenant('00000000-0000-4000-8000-00000000be01', 'varejo');
select tests.add_member('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000d0001', 'admin');
select tests.add_member('00000000-0000-4000-8000-00000000ac01', '00000000-0000-4000-8000-0000000d0002', 'analyst');
select tests.add_member('00000000-0000-4000-8000-00000000be01', '00000000-0000-4000-8000-0000000d0003', 'admin');

-- Canais: só gestor com MFA cria; o webhook vai para o Vault e nem o id dele é legível.
select tests.authenticate_as('00000000-0000-4000-8000-0000000d0002', '00000000-0000-4000-8000-00000000ac01', 'analyst', 'aal2');
select throws_ok(
  $$select doctor.create_notification_channel('slack', 'Plantão', '{}', 'https://hooks.slack.com/services/T/B/x')$$,
  '42501', null, 'Analyst não cria canal'
);
select throws_ok(
  $$insert into doctor.alert_rules (name, conditions) values ('Crítico', '{"type": "incident"}')$$,
  '42501', null, 'Analyst não cria Regra'
);
select tests.clear_authentication();
select tests.authenticate_as('00000000-0000-4000-8000-0000000d0001', '00000000-0000-4000-8000-00000000ac01', 'admin', 'aal2');
select ok(
  doctor.create_notification_channel('slack', 'Plantão', '{}', 'https://hooks.slack.com/services/T/B/x') is not null,
  'Admin cria canal do Slack'
);
select throws_ok($$select secret_id from doctor.notification_channels$$, '42501', null, 'o id do segredo não é legível');
select lives_ok(
  $$insert into doctor.alert_rules (name, conditions, channels)
    values ('Crítico em prd', '{"type": "incident", "min_severity": "critical"}',
      (select jsonb_agg(id) from doctor.notification_channels))$$,
  'Admin cria Regra'
);
select throws_ok(
  $$select doctor.create_notification_channel('slack', 'Sem webhook', '{}', null)$$,
  '23514', null, 'Slack sem webhook não entra'
);
-- Push: o próprio aparelho, e só ele.
select lives_ok(
  $$insert into doctor.push_subscriptions (endpoint, p256dh, auth) values ('https://push.test/a', repeat('p', 87), repeat('a', 22))$$,
  'Usuário assina o push do aparelho'
);
select tests.clear_authentication();
select tests.authenticate_as('00000000-0000-4000-8000-0000000d0002', '00000000-0000-4000-8000-00000000ac01', 'analyst', 'aal2');
select is((select count(*)::int from doctor.push_subscriptions), 0, 'colega não vê o aparelho de outro');
select is((select count(*)::int from doctor.alert_rules), 1, 'todo Papel vê as Regras');
select is((select count(*)::int from doctor.notification_deliveries), 0, 'histórico de entregas só para gestores');
select tests.clear_authentication();
select tests.authenticate_as('00000000-0000-4000-8000-0000000d0003', '00000000-0000-4000-8000-00000000be01', 'admin', 'aal2');
select is((select count(*)::int from doctor.alert_rules) + (select count(*)::int from doctor.notification_channels), 0,
  'outra Organização não vê Regras nem canais');
select tests.clear_authentication();

-- `alert.evaluate` nasce com o que pode notificar.
insert into doctor.outbox_messages (tenant_id, topic, payload)
values ('00000000-0000-4000-8000-00000000ac01', 'incident.opened', '{"incident_id": "00000000-0000-4000-8000-000000000999"}');
select is(
  (select payload ->> 'source' from doctor.outbox_messages where topic = 'alert.evaluate'
   and payload ->> 'incident_id' = '00000000-0000-4000-8000-000000000999'),
  'incident.opened', 'Incidente aberto pede avaliação dos alertas'
);
insert into doctor.integrations (id, tenant_id, name, source_system, target_system, environment)
values ('00000000-0000-4000-8000-0000000001a1', '00000000-0000-4000-8000-00000000ac01', 'Pedidos', 'salesforce', 'sap', 'prd');
insert into doctor.connectors (id, tenant_id, integration_id, provider, name)
values ('00000000-0000-4000-8000-0000000005a1', '00000000-0000-4000-8000-00000000ac01',
  '00000000-0000-4000-8000-0000000001a1', 'gcp', 'Logging');
update doctor.connectors set status = 'failing' where id = '00000000-0000-4000-8000-0000000005a1';
update doctor.connectors set consecutive_failures = 2 where id = '00000000-0000-4000-8000-0000000005a1';
select is(
  (select count(*)::int from doctor.outbox_messages where topic = 'alert.evaluate'
   and payload ->> 'connector_id' = '00000000-0000-4000-8000-0000000005a1'),
  1, 'Conector em failing pede avaliação uma vez'
);
select is(
  (select count(*)::int from doctor.outbox_messages where topic = 'alert.evaluate'
   and payload ->> 'source' = 'alert.evaluate'),
  0, 'a mensagem nova não dispara a si mesma'
);

select * from finish();
rollback;
