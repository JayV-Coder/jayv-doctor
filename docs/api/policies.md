# Políticas da Organização

Ticket #49. Ver e mudar é do Owner ou do Admin com `aal2`; o `PUT` aceita `Idempotency-Key`.

| Rota | Efeito |
|---|---|
| `GET /api/v1/policies` | `{ require_mfa }` |
| `PUT /api/v1/policies` | `{ require_mfa }` liga ou desliga o MFA obrigatório para todos os Papéis → a política gravada. A trilha de auditoria registra a mudança |

Com `require_mfa` ligado, sessão sem o segundo fator (`aal1`) não lê nem grava nada da Organização: toda rota com Organização responde `403 mfa_required`, as leituras diretas do site (`doctor_read`, ADR-0026) falham com o SQLSTATE `DR112`, e o RLS não devolve linhas (o Realtime também). O `GET /me` continua respondendo, com `mfa_required: true`, para o site mandar configurar o app autenticador. Os workers, que agem sem Usuário, não são afetados.

| Status | `code` | Quando |
|---|---|---|
| 403 | `forbidden` | Papel diferente de Owner ou Admin |
| 403 | `mfa_required` | Sessão `aal1` (para mudar a política, ou em qualquer rota com a política ligada) |
| 422 | `validation_error` | Campo desconhecido no corpo |
