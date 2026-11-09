-- Ticket #37: pausa pelo limite diário de API do provedor (Salesforce a 80%). O Conector não
-- falhou: fica pausado, visível na tela, e o agendador o retoma na janela seguinte.
alter table doctor.connectors drop constraint connectors_paused_reason_check;
alter table doctor.connectors
  add constraint connectors_paused_reason_check
  check (paused_reason in ('auth', 'manual', 'api_limit'));

create index connectors_api_limit_idx on doctor.connectors (next_run_at)
  where status = 'paused' and paused_reason = 'api_limit';
