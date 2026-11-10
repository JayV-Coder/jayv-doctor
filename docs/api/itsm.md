# Chamados (ITSM): Jira Service Management e ServiceNow

Tickets #43 (Jira) e #44 (ServiceNow). Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa; as rotas que mudam algo aceitam `Idempotency-Key`. Operação em [docs/operations/itsm.md](../operations/itsm.md).

| Rota | Quem | Efeito |
|---|---|---|
| `GET /api/v1/itsm/jira` | todo Papel | Conexão (ou `null`): status, sites autorizados, projeto, tipo, prioridades, campos fixos, sincronização |
| `POST /api/v1/itsm/jira/authorize` | Owner/Admin `aal2` | `{ url }` do consentimento no Atlassian, com `state` de uso único (10 min) |
| `POST /api/v1/itsm/jira/callback` | Owner/Admin `aal2` | `{ code, state }`: troca pelos tokens (no Vault, nunca na resposta) e lista os sites |
| `PUT /api/v1/itsm/jira` | Owner/Admin `aal2` | `{ cloud_id, project_key, issue_type, priority_map?, custom_fields?, sync_status? }`: ativa e registra o webhook do Jira |
| `DELETE /api/v1/itsm/jira` | Owner/Admin `aal2` | Desconecta e tira os tokens do Vault |
| `GET /api/v1/itsm/servicenow` | todo Papel | Conexão (ou `null`): instância, client id, `impact_map`, `assignment_groups`, `default_group`, sincronização (nunca o secret) |
| `PUT /api/v1/itsm/servicenow` | Owner/Admin `aal2` | `{ instance_url, client_id, client_secret?, impact_map?, assignment_groups?, default_group?, sync_status?, rotate_hook? }` → `{ connection, hook_url }` |
| `DELETE /api/v1/itsm/servicenow` | Owner/Admin `aal2` | Desconecta e tira as credenciais do Vault |
| `GET /api/v1/incidents/{id}/tickets` | todo Papel | Chamados do Incidente: `provider`, `status` (`creating`, `open`, `done`, `failed`), `external_key`, `url`, `external_status`, `assignment_group` |
| `POST /api/v1/incidents/{id}/tickets?provider=jira\|servicenow` | Analyst ou acima | "Abrir chamado" → `202`; uma vez por Incidente e provedor (repetir não abre outro). Sem `provider`, Jira |

- `409 itsm_not_configured`: sem conexão ativa (Jira com projeto, ServiceNow com instância) do provedor pedido. `409 conflict`: duas configurações do ServiceNow ao mesmo tempo. `400 invalid_state`: `state` usado, vencido ou de outra sessão. `503 jira_unavailable`: o app OAuth da plataforma não está configurado.
- ServiceNow: `instance_url` só `https://<instância>.service-now.com`. `client_secret` é obrigatório na primeira vez e quando a instância ou o client id mudam (`422 secret_required`); em branco, mantém o do Vault. `assignment_groups`: `{ "sap" | "salesforce" | "gcp" | "other": "<nome ou sys_id do grupo>" }`; `default_group` vale para "Indeterminado" e Sistemas sem grupo. `impact_map`: severidade → `{ impact, urgency }` (1 a 3). `hook_url` volta só na primeira configuração ou com `rotate_hook: true` (o anterior deixa de valer).
- `custom_fields`: `{ "customfield_10010": "valor" }`, só ids `customfield_<número>`, com valor fixo.
- `priority_map`: severidade → nome da prioridade no Jira (padrão `Highest`, `High`, `Medium`, `Low`).
- **Regra de alerta** (#41) com um canal do tipo `jira` ou `servicenow` abre o chamado do Incidente pela mesma reserva única.
- `POST /api/v1/itsm/jira/hooks/{token}`: o webhook do Jira (sem sessão). Responde sempre `204` e só pede a sincronização: status e comentários são lidos da API do Jira com os tokens da Organização.
- `POST /api/v1/itsm/servicenow/hooks/{token}`: a Business Rule do cliente, com `{ "number": "INC0010001" }`. Sempre `204`; só pede a leitura do incident pela Table API.
