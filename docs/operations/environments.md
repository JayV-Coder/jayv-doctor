# Ambientes

| Ambiente | Supabase (ref) | Região | Situação |
|---|---|---|---|
| dev | `fpkmpunbrtprjxiekten` (`jayv-doctor`) | `us-west-2` (Oregon) | ativo · migrações do ticket #2 aplicadas |
| staging | a criar | `sa-east-1` | — |
| prod | a criar | `sa-east-1` · PITR ligado | — |

**Atenção, residência de dados:** o ADR-0001 define São Paulo (`sa-east-1`) por causa da LGPD. O projeto dev está em Oregon, o que serve para desenvolvimento **apenas com dados sintéticos**. A região de um projeto Supabase não pode ser alterada depois da criação, então staging e prod precisam nascer em `sa-east-1`.

## Aplicar migrações

```bash
supabase link --project-ref <ref>
supabase db push        # aplica supabase/migrations pendentes
supabase migration list # confere o histórico local × remoto
```

## Ligar o Custom Access Token Hook

`supabase db push` aplica a migração, mas **não** liga o hook. Sem ele, o JWT não traz `tenant_id`: depois de criar ou trocar de Organização, o Usuário continua sem Organização ativa e o RLS não devolve nada. Em cada projeto hospedado, em Authentication → Hooks → Customize Access Token, escolha o schema `app` e a função `custom_access_token_hook`.

Computação no GCP: [gcp.md](gcp.md).
