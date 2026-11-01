# Ambientes

Todos os ambientes usam o projeto Supabase `exvsozyemolrjbjetqww` (`jayv-coder`, `sa-east-1`), no schema `doctor`, junto com o jayv-coder em produção. Decisão e consequências: [ADR-0009](../adr/0009-doctor-no-projeto-supabase-do-jayv-coder.md). **Esse banco tem dados reais:** dev e staging não são isolados de prod.

## Aplicar migrações

Nunca use `supabase db push` nem `apply_migration`: eles gravam ou comparam `supabase_migrations.schema_migrations`, que é do jayv-coder. Aplique cada arquivo de `supabase/migrations`, em ordem, **exceto** `00000000000000_shared_public_stub.sql`, numa transação, e registre a versão em `doctor.schema_migrations`.

Toda aplicação nesse projeto precisa de janela combinada com o responsável pelo jayv-coder.

## Ligar o Custom Access Token Hook

`config.toml` só vale localmente. Sem o hook, o JWT não traz `tenant_id` e o Doctor não funciona. No projeto, em Authentication → Hooks → Customize Access Token, escolha o schema `doctor` e a função `custom_access_token_hook`. Toda emissão de token do jayv-coder passa a usá-lo; faça isso em janela combinada, depois de aplicar as migrações, e confirme o login do jayv-coder em seguida.

## Configuração de Auth compartilhada

Templates de e-mail, política de senha e TOTP são do projeto. Não copie `supabase/templates` nem os limites do `config.toml` para lá sem revisar o efeito no jayv-coder. As URLs do Doctor devem ser **acrescentadas** à lista de redirecionamento.
