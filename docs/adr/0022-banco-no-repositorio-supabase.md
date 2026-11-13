# Banco no repositório JayV-Coder/supabase

As migrações e os testes de banco do Doctor saem deste repositório e passam a morar em `JayV-Coder/supabase`, junto com os do jayv-coder. Aqui o repositório entra como submódulo em `vendor/supabase`, e `supabase/migrations` e `supabase/tests` são links para lá; `supabase/config.toml` e o `seed.sql` continuam aqui, porque descrevem a stack local do Doctor.

No mesmo movimento, o `public` passou a ser o schema compartilhado entre os apps (conta, Organizações, i18n e cobrança), e o que é só do app do jayv-coder foi para o schema `coder`, com views de compatibilidade em `public` durante a transição. O Doctor continua no schema `doctor` e só lê `public.organizations`, `public.organization_members` e `public.profiles` (ADR-0009).

## Consequências

- **Migração nova do Doctor** nasce em `JayV-Coder/supabase` como `migrations/<versão>_doctor_<nome>.sql` e o teste em `tests/doctor/`. A PR daqui sobe o submódulo para o commit que a traz.
- **Dois aplicadores, separados pelo nome.** Em `JayV-Coder/supabase`, merge na `main` é deploy: o workflow roda `supabase db push` e aplica as migrações dos outros schemas, deixando de fora os arquivos `^[0-9]+_doctor_`. As do Doctor continuam com `scripts/apply-doctor-migrations.py`, que escolhe só esses arquivos e registra em `doctor.schema_migrations`, na janela combinada (ADR-0009). O `Conferir migrations` de lá recusa uma migração que mexa no schema `doctor` sem o nome.
- **O submódulo aponta para um commit da `main` de lá.** Um commit só de branch some quando a branch é apagada, e o checkout do CI falha. Enquanto a PR de lá não entra, a PR daqui fica em rascunho.
- **Sem o submódulo, o script falha** (`git submodule update --init`), em vez de dizer que não há nada pendente. Ele também avisa quando o deploy de lá ainda não aplicou uma migração anterior às pendentes do Doctor.
- **Sem stub de `public`:** a stack local e o CI rodam as migrações reais do jayv-coder, então uma mudança lá que quebre o Doctor aparece nos testes dos dois repositórios.
- **CI** faz checkout com `submodules: true` nos jobs que sobem o Supabase local (banco e E2E). O repositório `supabase` é público.

## Considered Options

- **Manter as migrações aqui e copiar para lá:** duas fontes para o mesmo banco.
- **Ignorar o submódulo e baixar o `supabase` no CI:** sem versão fixa, uma PR do jayv-coder quebraria o CI daqui sem aviso.
