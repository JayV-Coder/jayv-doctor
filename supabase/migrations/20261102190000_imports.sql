-- Ticket #11: Importação manual de logs. Logs brutos no Storage, Importações e outbox.

-- Para funções e políticas: o Papel do Usuário na Organização ativa, lido da tabela (a claim pode
-- estar atrasada). security definer: lê o Vínculo sem depender do RLS de memberships.
create function doctor.has_member_role(variadic roles text[])
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from doctor.memberships m
    where m.tenant_id = doctor.current_tenant_id()
      and m.user_id = auth.uid()
      and m.role = any (roles)
  )
$$;

revoke all on function doctor.has_member_role(text[]) from public, service_role;
grant execute on function doctor.has_member_role(text[]) to authenticated;

-- Log bruto: o arquivo como chegou, antes da Sanitização. Só a plataforma escreve.
create table doctor.raw_log_objects (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references doctor.tenants (id) on delete cascade,
  storage_path text not null unique check (split_part(storage_path, '/', 1) = tenant_id::text),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes bigint not null check (size_bytes between 0 and 52428800),
  source text not null check (source in ('import', 'connector', 'api')),
  -- Retenção padrão de 30 dias; a política por Organização chega no ticket #29.
  expires_at timestamptz not null default now() + interval '30 days',
  created_at timestamptz not null default now(),
  unique (tenant_id, id)
);
comment on table doctor.raw_log_objects is 'Log bruto no Storage (bucket doctor-raw-logs), antes da Sanitização.';

create index raw_log_objects_expires_at_idx on doctor.raw_log_objects (tenant_id, expires_at);

create table doctor.imports (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references doctor.tenants (id) on delete cascade,
  integration_id uuid not null,
  raw_log_object_id uuid,
  filename text not null check (char_length(filename) between 1 and 255),
  size_bytes bigint not null check (size_bytes >= 0),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  format text check (format in ('json', 'ndjson', 'csv')),
  -- `pending`: criada, esperando o upload. As demais seguem o ticket #11.
  status text not null default 'pending'
    check (status in ('pending', 'uploaded', 'processing', 'done', 'failed', 'rejected')),
  duplicate_of uuid,
  total_lines integer not null default 0,
  accepted integer not null default 0,
  rejected integer not null default 0,
  duplicates integer not null default 0,
  secrets_removed integer not null default 0,
  error text check (char_length(error) <= 500),
  created_by uuid default auth.uid() references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, integration_id) references doctor.integrations (tenant_id, id),
  foreign key (tenant_id, raw_log_object_id) references doctor.raw_log_objects (tenant_id, id),
  foreign key (tenant_id, duplicate_of) references doctor.imports (tenant_id, id)
);
comment on table doctor.imports is 'Importação manual: um arquivo de logs enviado para uma Integração.';

create index imports_tenant_created_idx on doctor.imports (tenant_id, created_at desc);
create index imports_tenant_sha256_idx on doctor.imports (tenant_id, integration_id, sha256);

create trigger imports_set_updated_at
before update on doctor.imports
for each row execute function doctor.set_updated_at();

-- Outbox (ADR-0001): a mensagem nasce na mesma transação do dado e um relay a publica no Pub/Sub.
create table doctor.outbox_messages (
  id bigint generated always as identity primary key,
  tenant_id uuid not null references doctor.tenants (id) on delete cascade,
  topic text not null check (topic ~ '^[a-z]+(\.[a-z]+)+$'),
  payload jsonb not null,
  created_at timestamptz not null default now(),
  published_at timestamptz,
  attempts integer not null default 0
);
comment on table doctor.outbox_messages is 'Mensagens a publicar no Pub/Sub; só a plataforma lê e escreve.';

create index outbox_messages_pending_idx on doctor.outbox_messages (id) where published_at is null;

alter table doctor.raw_log_objects enable row level security;
alter table doctor.imports enable row level security;
alter table doctor.outbox_messages enable row level security;

-- Escrita só pelas funções abaixo (e pelos workers, com service_role).
revoke all on doctor.raw_log_objects, doctor.imports, doctor.outbox_messages from anon, authenticated;
grant select on doctor.imports to authenticated;
grant select on doctor.raw_log_objects to authenticated;

create policy imports_select on doctor.imports
for select to authenticated
using (tenant_id = (select doctor.current_tenant_id()));

create policy raw_log_objects_select on doctor.raw_log_objects
for select to authenticated
using (
  tenant_id = (select doctor.current_tenant_id())
  and (select doctor.has_member_role('owner', 'admin', 'analyst'))
);

-- security definer: cria a Importação conferindo Papel (da tabela), Integração ativa, formato,
-- tamanho e duplicidade. Formato e tamanho errados viram Importação `rejected`, com o motivo,
-- para o histórico mostrar a tentativa.
create function doctor.create_import(integration_id uuid, filename text, size_bytes bigint, sha256 text)
returns table (id uuid, status text, format text, error text, duplicate_of uuid, storage_path text)
language plpgsql
security definer
set search_path = ''
as $$
declare
  tenant uuid := doctor.current_tenant_id();
  extension text := lower(substring(create_import.filename from '\.([A-Za-z0-9]+)$'));
  detected text;
  reason text;
  previous uuid;
  new_id uuid;
begin
  if tenant is null or not doctor.has_member_role('owner', 'admin', 'analyst') then
    raise insufficient_privilege using message = 'Papel não importa logs';
  end if;
  if create_import.filename ~ '[/\\]' or create_import.filename ~ '^\.' or create_import.filename ~ '[[:cntrl:]]' then
    raise invalid_parameter_value using message = 'nome de arquivo inválido';
  end if;
  if not exists (
    select 1 from doctor.integrations i
    where i.id = create_import.integration_id and i.tenant_id = tenant and i.archived_at is null
  ) then
    raise no_data_found using message = 'Integração não encontrada';
  end if;

  if extension in ('json', 'ndjson', 'csv') then
    detected := extension;
  else
    reason := 'Formato não permitido';
  end if;
  if reason is null and create_import.size_bytes > 52428800 then
    reason := 'Arquivo acima de 50 MB';
  end if;
  if reason is null then
    select i.id into previous from doctor.imports i
    where i.tenant_id = tenant
      and i.integration_id = create_import.integration_id
      and i.sha256 = create_import.sha256
      and i.status in ('uploaded', 'processing', 'done')
    order by i.created_at
    limit 1;
    if previous is not null then
      reason := 'Arquivo já importado nesta Integração';
    end if;
  end if;

  insert into doctor.imports (tenant_id, integration_id, filename, size_bytes, sha256, format, status, error, duplicate_of)
  values (
    tenant, create_import.integration_id, create_import.filename, create_import.size_bytes,
    create_import.sha256, detected, case when reason is null then 'pending' else 'rejected' end,
    reason, previous
  )
  returning imports.id into new_id;

  return query
  select i.id, i.status, i.format, i.error, i.duplicate_of,
    case when i.status = 'pending' then tenant || '/imports/' || i.id || '/' || i.filename end
  from doctor.imports i where i.id = new_id;
end;
$$;

-- security definer: marca o upload como concluído, registra o Log bruto e enfileira o
-- processamento na outbox, numa transação só. O tamanho é o que o Storage informou à API.
create function doctor.complete_import(target uuid, stored_size bigint)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  tenant uuid := doctor.current_tenant_id();
  pending_import doctor.imports;
  path text;
  raw_id uuid;
begin
  if tenant is null or not doctor.has_member_role('owner', 'admin', 'analyst') then
    raise insufficient_privilege using message = 'Papel não importa logs';
  end if;
  select * into pending_import from doctor.imports i where i.id = target and i.tenant_id = tenant for update;
  if not found then
    raise no_data_found using message = 'Importação não encontrada';
  end if;
  if pending_import.status <> 'pending' then
    raise exception 'Importação não está pendente' using errcode = 'DR005';
  end if;

  path := tenant || '/imports/' || pending_import.id || '/' || pending_import.filename;
  insert into doctor.raw_log_objects (tenant_id, storage_path, sha256, size_bytes, source)
  values (tenant, path, pending_import.sha256, stored_size, 'import')
  returning id into raw_id;

  update doctor.imports
  set status = 'uploaded', raw_log_object_id = raw_id, size_bytes = stored_size
  where id = pending_import.id;

  insert into doctor.outbox_messages (tenant_id, topic, payload)
  values (
    tenant, 'ingestion.raw',
    jsonb_build_object('import_id', pending_import.id, 'raw_log_object_id', raw_id, 'storage_path', path)
  );
end;
$$;

-- security definer: recusa uma Importação pendente cujo conteúdo não bate com o formato. Se o
-- arquivo chegou ao Storage, ele vira Log bruto já vencido: a retenção (ticket #29) o apaga, e
-- nada fica no bucket sem registro.
create function doctor.reject_import(target uuid, reason text, stored_size bigint default null)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  tenant uuid := doctor.current_tenant_id();
  pending_import doctor.imports;
  raw_id uuid;
begin
  if tenant is null or not doctor.has_member_role('owner', 'admin', 'analyst') then
    raise insufficient_privilege using message = 'Papel não importa logs';
  end if;
  select * into pending_import from doctor.imports i
  where i.id = target and i.tenant_id = tenant and i.status = 'pending' for update;
  if not found then
    raise no_data_found using message = 'Importação pendente não encontrada';
  end if;
  if stored_size is not null then
    insert into doctor.raw_log_objects (tenant_id, storage_path, sha256, size_bytes, source, expires_at)
    values (
      tenant, tenant || '/imports/' || pending_import.id || '/' || pending_import.filename,
      pending_import.sha256, least(stored_size, 52428800), 'import', now()
    )
    returning id into raw_id;
  end if;
  update doctor.imports
  set status = 'rejected', error = left(reason, 500), raw_log_object_id = raw_id
  where id = pending_import.id;
end;
$$;

revoke all on function doctor.create_import(uuid, text, bigint, text) from public, service_role;
revoke all on function doctor.complete_import(uuid, bigint) from public, service_role;
revoke all on function doctor.reject_import(uuid, text, bigint) from public, service_role;
grant execute on function doctor.create_import(uuid, text, bigint, text) to authenticated;
grant execute on function doctor.complete_import(uuid, bigint) to authenticated;
grant execute on function doctor.reject_import(uuid, text, bigint) to authenticated;

-- Bucket privado do Doctor no Storage, que é do projeto inteiro (ADR-0009): nome com prefixo e
-- políticas restritas a ele, sem efeito nos buckets do jayv-coder.
insert into storage.buckets (id, name, public, file_size_limit)
values ('doctor-raw-logs', 'doctor-raw-logs', false, 52428800)
on conflict (id) do nothing;

-- Caminho: {tenant_id}/imports/{import_id}/{arquivo}. Sobe só quem importa, só na pasta da
-- Organização ativa e só para uma Importação pendente dela.
create policy doctor_raw_logs_insert on storage.objects
for insert to authenticated
with check (
  bucket_id = 'doctor-raw-logs'
  and (storage.foldername(name))[1] = (select doctor.current_tenant_id())::text
  and (storage.foldername(name))[2] = 'imports'
  and (select doctor.has_member_role('owner', 'admin', 'analyst'))
  and exists (
    select 1 from doctor.imports i
    where i.tenant_id = (select doctor.current_tenant_id())
      and i.id::text = (storage.foldername(name))[3]
      and i.status = 'pending'
      and name = i.tenant_id || '/imports/' || i.id || '/' || i.filename
  )
);

-- Lê (a API confere o conteúdo ao concluir) só quem importa, na pasta da Organização ativa.
create policy doctor_raw_logs_select on storage.objects
for select to authenticated
using (
  bucket_id = 'doctor-raw-logs'
  and (storage.foldername(name))[1] = (select doctor.current_tenant_id())::text
  and (select doctor.has_member_role('owner', 'admin', 'analyst'))
);
