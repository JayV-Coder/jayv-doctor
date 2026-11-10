# Chamados (ITSM): Jira Service Management

Ticket #43. Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa; as rotas que mudam algo aceitam `Idempotency-Key`. Operação em [docs/operations/itsm.md](../operations/itsm.md).

| Rota | Quem | Efeito |
|---|---|---|
| `GET /api/v1/itsm/jira` | todo Papel | Conexão (ou `null`): status, sites autorizados, projeto, tipo, prioridades, campos fixos, sincronização |
| `POST /api/v1/itsm/jira/authorize` | Owner/Admin `aal2` | `{ url }` do consentimento no Atlassian, com `state` de uso único (10 min) |
| `POST /api/v1/itsm/jira/callback` | Owner/Admin `aal2` | `{ code, state }`: troca pelos tokens (no Vault, nunca na resposta) e lista os sites |
| `PUT /api/v1/itsm/jira` | Owner/Admin `aal2` | `{ cloud_id, project_key, issue_type, priority_map?, custom_fields?, sync_status? }`: ativa e registra o webhook do Jira |
| `DELETE /api/v1/itsm/jira` | Owner/Admin `aal2` | Desconecta e tira os tokens do Vault |
| `GET /api/v1/incidents/{id}/tickets` | todo Papel | Chamados do Incidente: `status` (`creating`, `open`, `done`, `failed`), `external_key`, `url`, `external_status` |
| `POST /api/v1/incidents/{id}/tickets` | Analyst ou acima | "Abrir chamado no Jira" → `202`; uma vez por Incidente (repetir não abre outro) |

- `409 jira_not_configured`: sem conexão ativa com projeto. `400 invalid_state`: `state` usado, vencido ou de outra sessão. `503 jira_unavailable`: o app OAuth da plataforma não está configurado.
- `custom_fields`: `{ "customfield_10010": "valor" }`, só ids `customfield_<número>`, com valor fixo.
- `priority_map`: severidade → nome da prioridade no Jira (padrão `Highest`, `High`, `Medium`, `Low`).
- **Regra de alerta** (#41) com um canal do tipo `jira` abre o chamado do Incidente pela mesma reserva única.
- `POST /api/v1/itsm/jira/hooks/{token}`: o webhook do Jira (sem sessão). Responde sempre `204` e só pede a sincronização: status e comentários são lidos da API do Jira com os tokens da Organização.
