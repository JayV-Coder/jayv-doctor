# Organizações

Exigem `Authorization: Bearer <JWT do Supabase Auth>`. As claims de tenant só mudam na renovação: depois de `201` ou `204`, o cliente chama `refreshSession()`.

## `POST /api/v1/orgs`

Cria a Organização, o Vínculo Owner e a torna ativa numa só transação. `tenant_id` e Papel nunca vêm do payload: campos extras respondem `422`.

```json
{
  "name": "Acme Consultoria",
  "slug": "acme-consultoria",
  "segment": "Varejo",
  "llm_provider": "anthropic",
  "dpa_accepted": true
}
```

Responde `201` com `{ "id": "uuid" }`. O aceite do DPA é gravado em `tenants.dpa_accepted_at`; `dpa_accepted` diferente de `true` responde `422`.

## `POST /api/v1/orgs/{id}/enable`

Ativa o Doctor numa Organização que já existe no jayv-coder (ADR-0025), sem criar outra: nome e identificador são os de lá. Só o owner do jayv-coder ativa. Todos os membros ganham o Vínculo com o Papel equivalente, e a Organização fica ativa para quem ativou.

```json
{ "segment": "Indústria", "llm_provider": "anthropic", "dpa_accepted": true }
```

Responde `201` com `{ "id": "uuid" }`. Campos extras (nome, Papel, tenant) e `dpa_accepted` diferente de `true` respondem `422`.

## `POST /api/v1/orgs/{id}/switch`

Torna `{id}` a Organização ativa, se houver Vínculo. Responde `204`.

## Erros (`application/problem+json`)

| Status | `code` | Quando |
|---|---|---|
| 401 | `unauthorized` | Token ausente, inválido ou expirado |
| 403 | `not_a_member` | `switch` para Organização sem Vínculo; as claims não mudam |
| 403 | `not_owner` | `enable` por quem é da Organização no jayv-coder sem ser owner |
| 404 | `not_found` | `enable` de Organização que não existe ou de que o Usuário não é membro |
| 409 | `slug_taken` | Identificador já usado por outra Organização |
| 409 | `already_enabled` | `enable` de Organização em que o Doctor já está ativo |
