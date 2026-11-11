# Ambientes

Todos os ambientes usam o projeto Supabase `exvsozyemolrjbjetqww` (`jayv-coder`, `sa-east-1`), no schema `doctor`, junto com o jayv-coder em produção. Decisão e consequências: [ADR-0009](../adr/0009-doctor-no-projeto-supabase-do-jayv-coder.md). **Esse banco tem dados reais:** dev e staging não são isolados de prod.

## Aplicar migrações

Nunca use `supabase db push` nem `apply_migration`: eles usam `supabase_migrations.schema_migrations`, que é do jayv-coder. Use o script, que confere as tabelas de `public`, aplica só as migrações `*_doctor_*` de `vendor/supabase` e registra cada versão em `doctor.schema_migrations`:

```bash
SUPABASE_DB_URL=<url direta> uv run python scripts/apply-doctor-migrations.py --check   # só leitura
SUPABASE_DB_URL=<url direta> uv run python scripts/apply-doctor-migrations.py --apply
```

Toda aplicação nesse projeto precisa de janela combinada com o responsável pelo jayv-coder.

## Ligar o Custom Access Token Hook

`config.toml` só vale localmente. Sem o hook, o JWT não traz `tenant_id` e o Doctor não funciona. O Supabase aceita um hook por projeto: **antes**, abra Authentication → Hooks e confirme que Customize Access Token está vazio. Se houver outro, pare: selecionar o do Doctor removeria as claims dele. Depois, escolha o schema `doctor` e a função `custom_access_token_hook`. Toda emissão de token do jayv-coder passa a usá-lo; faça isso em janela combinada, depois de aplicar as migrações, e confirme o login do jayv-coder em seguida.

## Configuração de Auth compartilhada

Templates de e-mail, política de senha e TOTP são do projeto. Não copie `supabase/templates` nem os limites do `config.toml` para lá sem revisar o efeito no jayv-coder. As URLs do Doctor devem ser **acrescentadas** à lista de redirecionamento, com curinga: `https://<app>/auth/callback**`.

Computação no GCP: [gcp.md](gcp.md).
