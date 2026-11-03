-- Tela de Conectores (ticket #16): o Checkpoint e o motivo da pausa aparecem no card, e o status
-- chega em tempo real pelo Realtime.

-- Sem secret_id, como antes: nem o id do segredo vai para o cliente.
grant select (checkpoint, paused_reason) on doctor.connectors to authenticated;

-- O Realtime confere o RLS e os privilégios de coluna de quem assina (`realtime.apply_rls`), então
-- o evento traz só as colunas acima, e só para a Organização do JWT. A publicação é do projeto
-- inteiro (compartilhado com o jayv-coder, ADR-0009): só se acrescenta a tabela do Doctor.
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
    and not exists (
      select 1 from pg_publication_tables
      where pubname = 'supabase_realtime' and schemaname = 'doctor' and tablename = 'connectors'
    )
  then
    alter publication supabase_realtime add table doctor.connectors;
  end if;
end;
$$;
