# Membros e Convites

Exigem `Authorization: Bearer <JWT do Supabase Auth>`. Salvo `accept`, exigem Owner ou Admin com `aal2`. O Papel vale pelo que está no banco: quem foi rebaixado perde o acesso na hora, mesmo com JWT antigo.

| Rota | Efeito |
|---|---|
| `GET /api/v1/memberships` | Membros da Organização ativa |
| `PATCH /api/v1/memberships/{id}` | Muda o Papel: `{ "role": "viewer" }` |
| `DELETE /api/v1/memberships/{id}` | Tira o acesso ao Doctor; o Vínculo no jayv-coder continua |
| `GET /api/v1/invitations` | Convites pendentes |
| `POST /api/v1/invitations` | Convida: `{ "email": "...", "role": "analyst" }` → `201 { "id": "uuid" }` |
| `POST /api/v1/invitations/{id}/resend` | Gera outro token e reenvia; o anterior deixa de valer |
| `DELETE /api/v1/invitations/{id}` | Revoga |
| `POST /api/v1/invitations/accept` | Aceita: `{ "token": "..." }` → `{ "tenant_id": "uuid" }` |

O token vai no corpo, e não na URL como no ticket #6, para não entrar nos logs. Só o hash sha256 é guardado. Depois de aceitar, o cliente chama `refreshSession()`. O aceite exige sessão de quem confirmou o e-mail convidado, e não exige Organização ativa.

Admin não convida nem promove a Owner, e não altera nem remove um Owner.

## Erros (`application/problem+json`)

| Status | `code` | Quando |
|---|---|---|
| 401 | `unauthorized` | Token ausente, inválido ou expirado |
| 403 | `no_active_tenant` | Sem Organização ativa |
| 403 | `forbidden` | Papel não permite a ação |
| 403 | `mfa_required` | Sessão `aal1` |
| 403 | `invitation_email_mismatch` | Convite de outro e-mail, ou e-mail não confirmado |
| 404 | `not_found` | Convite ou membro inexistente nesta Organização |
| 409 | `last_owner` | Deixaria a Organização sem Owner |
| 409 | `already_invited` | Já há convite pendente para o e-mail |
| 409 | `already_member` | A pessoa já tem Papel |
| 410 | `invitation_gone` | Convite expirado ou usado |
| 503 | `mail_unavailable` | Convite criado, e-mail não enviado; use `resend` |
