# Integrações

Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. Todo Papel lista. Cadastrar, alterar e arquivar exigem Owner ou Admin com `aal2`, conforme a linha "Gerenciar integrações e conectores" da matriz do ticket #6. O banco confere de novo o Papel, lido da tabela (`doctor.is_manager()`), então quem foi rebaixado perde a escrita na hora, mesmo com JWT antigo.

| Rota | Efeito |
|---|---|
| `GET /api/v1/integrations` | Integrações da Organização ativa, sem as arquivadas; `?include_archived=true` inclui |
| `POST /api/v1/integrations` | Cadastra → `201` com a Integração |
| `PATCH /api/v1/integrations/{id}` | Altera só os campos enviados; `description` e `owner_team` aceitam `null` |
| `POST /api/v1/integrations/{id}/archive` | Arquiva → `200`; repetir mantém a data original |

Corpo do `POST`:

```json
{
  "name": "Pedidos Salesforce → SAP",
  "source_system": "salesforce",
  "target_system": "sap",
  "environment": "prd",
  "owner_team": "Squad Pedidos",
  "description": "Pedidos aprovados no Salesforce viram ordens de venda no SAP."
}
```

- `source_system` e `target_system`: `sap`, `salesforce`, `gcp` ou `other`. `environment`: `dev`, `hml` ou `prd`.
- O nome é único por Organização e Ambiente, contando as arquivadas. O mesmo nome vale em outra Organização.
- O payload não define tenant, autor nem arquivamento: campos extras viram `422`.
- Não há exclusão física, porque Execuções e Incidentes apontam para a Integração. Arquivada, ela some das listas padrão. Os Conectores (ticket #14) devem ignorar Integrações arquivadas ao sincronizar.
- `error_rate_24h` fica `null` até existirem Execuções (ticket #17): sem Execução não há taxa, nem 0%.

## Erros (`application/problem+json`)

| Status | `code` | Quando |
|---|---|---|
| 401 | `unauthorized` | Token ausente, inválido ou expirado |
| 403 | `no_active_tenant` | Sem Organização ativa |
| 403 | `forbidden` | Papel não permite a ação |
| 403 | `mfa_required` | Escrita com sessão `aal1` |
| 404 | `not_found` | Integração inexistente nesta Organização |
| 409 | `integration_exists` | Nome e Ambiente já usados nesta Organização |
| 422 | `validation_error` | Corpo inválido |
