# Plataforma da API

Vale para toda rota em `/api/v1`.

## Autenticação e Organização ativa

`Authorization: Bearer <JWT do Supabase Auth>`, validado pelo JWKS com cache. Sem token: `401 unauthorized`. Rotas de uma Organização sem `tenant_id` no JWT: `403 no_active_tenant`. Todo acesso a dados roda em `tenant_tx`, como `authenticated`, com o RLS valendo; um teste de integração confere que nenhuma rota usa `service_role`.

## `Idempotency-Key`

Em `POST`, `PATCH` e `DELETE`, dentro de uma Organização ativa, por Usuário:

- mesma chave e mesmo corpo: devolve a resposta gravada, sem novo efeito;
- mesma chave com outro corpo: `422 idempotency_key_reused`;
- mesma chave em paralelo: a segunda espera a primeira terminar e devolve a resposta dela.

Reserva, efeito e resposta gravada ficam na mesma transação: em erro, nada é gravado, e a próxima tentativa executa de verdade. A permissão é conferida antes de devolver uma resposta gravada. Respostas ficam 24 h; a limpeza é feita pela própria API.

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
