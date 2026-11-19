# `GET /api/v1/me`

Perfil, Organizações e Papel na Organização ativa do Usuário autenticado. Exige `Authorization: Bearer <JWT do Supabase Auth>`.

```json
{
  "id": "uuid",
  "email": "ana@acme.test",
  "aal": "aal2",
  "profile": { "full_name": "Ana Souza", "avatar_url": null, "locale": "pt-BR" },
  "organizations": [{ "id": "uuid", "name": "Acme", "slug": "acme", "role": "owner" }],
  "available_organizations": [{ "id": "uuid", "name": "Varejo", "slug": "varejo", "coder_role": "owner" }],
  "active_tenant_id": "uuid",
  "active_role": "owner",
  "mfa_required": false
}
```

`organizations` traz as Organizações em que o Usuário tem Papel no Doctor. Antes de listar, o `/me` dá o Vínculo que falta nas Organizações do jayv-coder em que o Doctor está ativo, com o Papel equivalente (owner → Owner, maintainer → Admin, member → Viewer), menos onde o Doctor removeu a pessoa (ADR-0025). `available_organizations` traz as Organizações do jayv-coder do Usuário em que o Doctor ainda não está ativo, com o Papel de lá (`coder_role`): só o owner as ativa (`POST /orgs/{id}/enable`). `mfa_required` é `true` quando a Organização do token exige MFA (#49, [policies.md](policies.md)) e a sessão é `aal1`: o `/me` responde mesmo assim, com `active_tenant_id` e `active_role` nulos (a Organização não está ativa sem o MFA), e o site manda configurar o app autenticador ou trocar de Organização. `profile` vem de `public.profiles` e é `null` numa sessão `aal1` de quem tem MFA verificado, até o código ser confirmado.

## Erros (`application/problem+json`)

| Status | `code` | Quando |
|---|---|---|
| 401 | `unauthorized` | Token ausente, inválido ou expirado |
| 403 | `mfa_required` | Ação administrativa com sessão `aal1` (dependência `require_aal2`) |
| 503 | `auth_unavailable` | Chaves do Auth indisponíveis; tente de novo sem encerrar a sessão |
