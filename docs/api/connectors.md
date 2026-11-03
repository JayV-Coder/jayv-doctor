# Conectores

Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. Todo Papel lê. Gerenciar exige Owner ou Admin com `aal2`, conforme a linha "Gerenciar integrações e conectores" da matriz do ticket #6, e o banco confere o Papel de novo na tabela.

| Rota | Efeito |
|---|---|
| `GET /api/v1/connectors` | Conectores da Organização ativa |
| `POST /api/v1/connectors` | `{ integration_id, provider, name, config, credential }` → `201` com o Conector, sem a credencial |
| `POST /api/v1/connectors/test` | Testa provedor, config e credencial **antes de salvar**; não grava nada → `{ ok, message }` |
| `GET /api/v1/connectors/{id}` | Um Conector |
| `PATCH /api/v1/connectors/{id}` | `name`, `config`, `sync_interval_seconds` (60 a 86400) e/ou `credential` |
| `POST /api/v1/connectors/{id}/test` | `{ credential }` → testa com a config salva |
| `POST /api/v1/connectors/{id}/sync` | Pede uma Sincronização agora → `202` |
| `POST /api/v1/connectors/{id}/pause` · `/resume` | Pausa; retoma (zera as falhas e roda já) → `204` |
| `GET /api/v1/connectors/{id}/syncs` | As 50 Sincronizações mais recentes |

- **Credencial:** vai direto para o Supabase Vault (ADR-0006) e **nenhuma resposta a traz, nem mascarada**. Nem o id do segredo é legível pelo cliente. Só o worker de Conectores a lê. Por isso o teste de um Conector salvo pede a credencial no corpo: ela é usada só para o teste e descartada.
- **Credencial nova** tira o Conector da pausa por erro de autenticação. **Config nova** recomeça a coleta do zero, e a deduplicação descarta o que repetir.
- **Config** é validada pelo conector do provedor. O erro traz o nome do campo e a regra, nunca o valor.
- `provider`: `fake`, `gcp`, `salesforce` ou `sap`. Hoje só o `fake` tem conector; os outros respondem `422 provider_unavailable` até os tickets #15, #37 e #38.

Status e política de falhas estão em [`docs/operations/conectores.md`](../operations/conectores.md).

## Erros (`application/problem+json`)

| Status | `code` | Quando |
|---|---|---|
| 403 | `forbidden`, `mfa_required`, `no_active_tenant` | Papel, MFA ou Organização |
| 404 | `not_found` | Conector ou Integração inexistente nesta Organização |
| 409 | `connector_paused` | `sync` de Conector pausado ou desativado |
| 422 | `invalid_config` | Config recusada pelo conector do provedor |
| 422 | `provider_unavailable` | Provedor ainda sem conector |
| 422 | `validation_error` | Corpo inválido |
