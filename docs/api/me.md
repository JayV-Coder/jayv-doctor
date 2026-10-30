# `GET /api/v1/me`

Perfil, Organizações e Papel na Organização ativa do Usuário autenticado. Exige `Authorization: Bearer <JWT do Supabase Auth>`.

```json
{
  "id": "uuid",
  "email": "ana@acme.test",
  "aal": "aal2",
  "profile": { "full_name": "Ana Souza", "avatar_url": null, "locale": "pt-BR" },
  "organizations": [{ "id": "uuid", "name": "Acme", "slug": "acme" }],
  "active_tenant_id": "uuid",
  "active_role": "owner"
}
```

Até o ticket #5, `organizations` traz só a Organização ativa.

## Erros (`application/problem+json`)

| Status | `code` | Quando |
|---|---|---|
| 401 | `unauthorized` | Token ausente, inválido ou expirado |
| 403 | `mfa_required` | Ação administrativa com sessão `aal1` (dependência `require_aal2`) |
| 503 | `auth_unavailable` | Chaves do Auth indisponíveis; tente de novo sem encerrar a sessão |
