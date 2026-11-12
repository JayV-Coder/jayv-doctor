# Banco no repositório JayV-Coder/supabase

As migrações e os testes de banco do Doctor saem deste repositório e passam a morar em `JayV-Coder/supabase`, junto com os do jayv-coder. Aqui o repositório entra como submódulo em `vendor/supabase`, e `supabase/migrations` e `supabase/tests` são links para lá; `supabase/config.toml` e o `seed.sql` continuam aqui, porque descrevem a stack local do Doctor.

No mesmo movimento, o `public` passou a ser o schema compartilhado entre os apps (conta, Organizações, i18n e cobrança), e o que é só do app do jayv-coder foi para o schema `coder`, com views de compatibilidade em `public` durante a transição. O Doctor continua no schema `doctor` e só lê `public.organizations`, `public.organization_members` e `public.profiles` (ADR-0009).

## Consequências

- **Migração nova do Doctor** nasce em `JayV-Coder/supabase` como `migrations/<versão>_doctor_<nome>.sql` e o teste em `tests/doctor/`. A PR daqui sobe o submódulo para o commit que a traz.
- **Aplicar** continua sendo `scripts/apply-doctor-migrations.py`, que agora escolhe só os arquivos `*_doctor_*` e registra em `doctor.schema_migrations`.
- **Sem stub de `public`:** a stack local e o CI rodam as migrações reais do jayv-coder, então uma mudança lá que quebre o Doctor aparece nos testes dos dois repositórios.
- **CI** faz checkout com `submodules: true`. O repositório `supabase` é público.

## Considered Options

- **Manter as migrações aqui e copiar para lá:** duas fontes para o mesmo banco.
- **Ignorar o submódulo e baixar o `supabase` no CI:** sem versão fixa, uma PR do jayv-coder quebraria o CI daqui sem aviso.
