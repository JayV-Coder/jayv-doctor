# Particionamento nativo dos Eventos, sem pg_partman

O ticket #12 pede `doctor.events` particionada por mês com `pg_partman`. No projeto Supabase compartilhado com o jayv-coder, instalar extensão exige aprovação (ADR-0009). Além disso, o `pg_partman` cria as partições futuras por um job agendado, e o `pg_cron` do projeto é do jayv-coder. Por isso usamos o particionamento declarativo do próprio Postgres (`partition by range (timestamp)`).

As partições são mensais e nascem sob demanda: antes de gravar um lote, o worker de ingestão chama `doctor.ensure_event_partition(dia)` para cada mês do lote. A função é idempotente e segura contra concorrência, e só a `service_role` a executa. A partição nasce com RLS e sem grant para o cliente, então os Eventos só são lidos pela tabela-mãe, com a política dela. Não há partição `DEFAULT`: com uma, criar depois a partição de um mês que já tem linhas nela falharia. Sem partição para o mês, o insert falha com erro, em vez de gravar no lugar errado.

## Consequências

- **Chaves únicas:** toda chave única inclui `timestamp`, a chave de partição. O alvo das FKs compostas para Eventos é `(tenant_id, id, timestamp)`, e a deduplicação usa `unique (tenant_id, dedup_key, timestamp)`. É a exceção à convenção `unique (tenant_id, id)`.
- **Importação histórica:** um mês antigo ganha partição na primeira vez que aparece. A retenção (ticket #29) apaga Eventos vencidos e remove as partições que ficarem vazias com `drop table`, sem `delete` linha a linha.
- **Partições futuras:** nada cria partição antes de haver Evento no mês, então não há job para manter. O custo é um `create table` no primeiro lote de cada mês.
- Se um dia o `pg_partman` for aprovado, ele pode adotar as partições existentes, porque o nome segue `events_AAAA_MM`.
