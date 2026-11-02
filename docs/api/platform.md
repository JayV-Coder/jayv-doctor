# Plataforma da API

Vale para toda rota em `/api/v1`.

## Autenticação e Organização ativa

`Authorization: Bearer <JWT do Supabase Auth>`, validado pelo JWKS com cache. Sem token: `401 unauthorized`. Rotas de uma Organização sem `tenant_id` no JWT: `403 no_active_tenant`. Todo acesso a dados roda em `tenant_tx`, como `authenticated`, com o RLS valendo; um teste de integração confere que nenhuma rota usa `service_role`.

## `Idempotency-Key`

Em `POST`, `PATCH` e `DELETE`, dentro de uma Organização ativa:

- mesma chave e mesmo corpo, do mesmo Usuário: devolve a resposta gravada, sem novo efeito;
- mesma chave com outro corpo ou outro Usuário: `422 idempotency_key_reused`;
- mesma chave ainda em execução: `409 idempotency_in_progress`.

Só respostas de sucesso ficam gravadas, por 24 h. Em erro, a chave é liberada e a próxima tentativa executa de verdade. Se a instância cair no meio, a chave fica presa por até 5 min, e o efeito pode se repetir depois disso.

## Rate limit

Token bucket por Organização e Usuário, em memória por instância: `RATE_LIMIT_PER_MINUTE` (padrão 120). Acima disso, `429 rate_limited` com `Retry-After`. O limite global por IP é do Cloud Armor.

## Erros

`application/problem+json` em pt-BR: `{ "status", "code", "title" }`. Validação responde `422 validation_error` sem ecoar a entrada; erro inesperado, `500 internal_error`, sem detalhes.

## Saúde

`GET /healthz` diz se o processo responde; `GET /readyz` também testa o banco (`503 not_ready`). Ficam fora dos traces.

## Telemetria

Com `OTEL_ENABLED=true` (no Cloud Run), traces vão para o Cloud Trace e métricas para o Cloud Monitoring. O span leva `tenant.id`; e-mail e nome nunca.

## Contrato

OpenAPI em `/api/v1/openapi.json`. `make contracts` grava `packages/contracts/openapi.json` e gera `src/generated/api.ts`, que o app web importa. O CI falha se o gerado divergir.
