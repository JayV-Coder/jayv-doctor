-- Explorador de Execuções (ticket #19): índices da lista e da busca, e o download auditado do
-- Log bruto.

-- Lista: as mais recentes da Organização, sem as fundidas, na ordem do cursor.
create index executions_list_idx on doctor.executions (tenant_id, first_event_at desc, id desc)
  where merged_into is null;
-- Busca por execution_id, trace_id ou Referência (HMAC) com `correlation_keys @> …`.
create index executions_keys_idx on doctor.executions using gin (correlation_keys jsonb_path_ops);

-- Download do Log bruto: Analyst ou acima (o Viewer não baixa), auditado. A URL assinada sai do
-- Storage com o JWT do próprio Usuário, e a política do bucket repete a regra do Papel.
create function doctor.request_raw_log_download(target uuid)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  tenant uuid := doctor.current_tenant_id();
  path text;
begin
  if not doctor.has_member_role('owner', 'admin', 'analyst') then
    raise insufficient_privilege using message = 'exige Analyst ou acima';
  end if;
  select r.storage_path into path
  from doctor.raw_log_objects r
  where r.tenant_id = tenant and r.id = target and r.expires_at > now();
  if path is null then
    raise no_data_found using message = 'Log bruto não encontrado ou vencido';
  end if;
  perform doctor.record_audit(tenant, 'raw_log.download', target::text);
  return path;
end;
$$;

revoke all on function doctor.request_raw_log_download(uuid) from public, service_role;
grant execute on function doctor.request_raw_log_download(uuid) to authenticated;
