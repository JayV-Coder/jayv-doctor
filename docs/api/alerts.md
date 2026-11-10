# Alertas e notificações

Ticket #41, [ADR-0017](../adr/0017-alertas-por-worker-proprio.md). Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. As rotas que mudam algo aceitam `Idempotency-Key`.

## Regras e canais (todo Papel lê; Owner e Admin com `aal2` mudam)

| Rota | Efeito |
|---|---|
| `GET /api/v1/alert-rules` | Regras da Organização |
| `POST /api/v1/alert-rules` | `{ name, enabled?, conditions, channels, quiet_hours? }` → `201` |
| `PATCH /api/v1/alert-rules/{id}` | qualquer campo; `clear_quiet_hours: true` tira o silêncio |
| `DELETE /api/v1/alert-rules/{id}` | `204` |
| `GET /api/v1/notification-channels` | Canais, sem o webhook |
| `POST /api/v1/notification-channels` | `{ type, name, audience? , webhook_url? }` → `201` |
| `DELETE /api/v1/notification-channels/{id}` | Remove o canal e o webhook do Vault → `204` |

- **`conditions`** (`422 invalid_alert` com o campo e a regra):
  - `{ "type": "incident", "min_severity": "critical", "environments": ["prd"], "integrations": [], "events": ["opened", "updated"] }`
  - `{ "type": "error_rate", "threshold_pct": 5, "minutes": 10, "min_executions": 10, "integrations": [] }`
  - `{ "type": "connector_failing", "integrations": [] }`
  - `{ "type": "diagnosis_review", "minutes": 30 }`
- **`channels`**: ids de canais desta Organização.
- **`quiet_hours`**: `{ "start": "22:00", "end": "07:00", "timezone": "America/Sao_Paulo" }`. Incidente crítico ignora o silêncio.
- **Canal**: `email` e `webpush` com `audience` (`managers` = Owners e Admins, ou `all`), sempre Usuários da Organização. `slack` e `teams` com `webhook_url` em `https://hooks.slack.com/…` ou `https://*.webhook.office.com/…`, `*.logic.azure.com`, `*.powerplatform.com`. O webhook vai para o Vault e não volta em nenhuma resposta.

## Push e silêncio (cada Usuário, os seus)

| Rota | Efeito |
|---|---|
| `GET /api/v1/push/key` | `{ public_key }` VAPID para o `pushManager.subscribe`; `null` sem push configurado |
| `GET /api/v1/push-subscriptions` | Aparelhos do próprio Usuário |
| `POST /api/v1/push-subscriptions` | `{ endpoint, keys: { p256dh, auth }, user_agent? }` → `201`; o mesmo `endpoint` substitui o anterior |
| `DELETE /api/v1/push-subscriptions/{id}` | `204` |
| `GET` / `PUT /api/v1/alert-preferences` | `{ quiet_hours }` do Usuário (silêncio fora do plantão) |

- `endpoint` só dos serviços de push dos navegadores (`fcm.googleapis.com`, `updates.push.services.mozilla.com`, `*.push.apple.com`, `*.notify.windows.com`): `422 invalid_alert` para outro.
- No iPhone (iOS 16.4+), o push só funciona com o PWA instalado na tela de início.
- Canais `jira` (#43) e `servicenow` (#44): sem configuração nem segredo; numa Regra de Incidente, abrem o chamado do Incidente no ITSM configurado em [itsm.md](itsm.md), uma vez só.
