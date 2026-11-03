# Trilha de auditoria

Owner ou Admin com MFA (`aal2`) da Organização ativa. A API confere o Papel e o banco repete a regra na política de `doctor.audit_logs`.

| Rota | Efeito |
|---|---|
| `POST /api/v1/audit-logs/search` | `{ q?, category?, since?, until?, cursor?, limit? }` → `{ items, next_cursor }`, do mais novo ao mais antigo |
| `POST /api/v1/audit-logs/export` | CSV (`occurred_at, actor_type, actor, action, resource_type, resource_id, before, after, ip`), até 50 mil registros, gerado enquanto é enviado; a exportação vira o registro `audit.exported` |

- **Por que POST:** o termo de busca pode ser o e-mail de alguém e não vai para a URL nem para os logs.
- **Categorias** (prefixo da ação): `security` (`membership.`, `invitation.`, `org.`, `auth.`, `ingestion_token.`), `diagnosis`, `connectors` (`connector.`, `integration.`, `vault.`), `data` (`raw_log.`, `knowledge.`, `audit.`, `report.`, `retention.`), `incidents`.
- **Ator:** `actor_type` é `user` (o JWT), `worker` (sessão `service_role`) ou `system`. O registro guarda só o id; o e-mail (`actor_label`) é resolvido na leitura.
- **Desvio do ticket:** a exportação é síncrona e em streaming, com o limite de 50 mil registros, e não um job assíncrono. A exportação assíncrona, com arquivo no Storage, chega com os Relatórios (#32), que trazem o bucket e o job.

## O que é registrado

- **Triggers** em `memberships`, `invitations`, `connectors`, `integrations` e `tenants` (`retention_policies` entra com o #29): `<entidade>.created/updated/deleted`, com `before` e `after` só das colunas que mudaram. A troca de Papel é `membership.role_changed`. Ficam de fora o e-mail e o hash do token do convite e o `secret_id` do Conector.
- **Ações de negócio:** `diagnosis.requested`, `diagnosis.reviewed` (veredito e versão), `raw_log.downloaded`, `knowledge.promoted`/`knowledge.deleted`, `org.switched`, `audit.exported`, `vault.secret_read` (worker lendo a credencial do Conector) e as dos Conectores.
- **Supabase Auth:** login, logout, recuperação e troca de senha e MFA, copiados uma vez por dia (`aid-audit-auth-events`, worker de correlação) para cada Organização do Usuário, com o IP.
- **Requisição:** IP (`X-Forwarded-For`), user agent e request id (`X-Request-Id` ou o trace do Cloud Run) vão da API ao banco em `doctor.request`, e um trigger preenche todo registro da transação.

## Imutabilidade e retenção

Append-only: nenhum papel altera um registro (`DR030`, até o `postgres`), e o `service_role` só lê e insere. Só a retenção (#29, com `doctor.retention = on` na transação) e a exclusão da própria Organização apagam. A tabela é particionada por mês (`audit_logs_YYYY_MM`, com uma partição padrão), e o job diário cria as partições do mês atual e dos dois seguintes. Retenção padrão: 365 dias.
