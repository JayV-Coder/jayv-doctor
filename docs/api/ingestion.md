# Ingestão por API

Para sistemas externos (SAP PI/PO, middleware, scripts) mandarem Eventos já no Contrato de evento v1 (`packages/contracts/schemas/event.v1.json`).

## Tokens de ingestão

Exigem JWT de Owner ou Admin com `aal2`, conforme a linha "Gerenciar integrações e conectores" da matriz do ticket #6.

| Rota | Efeito |
|---|---|
| `GET /api/v1/ingestion-tokens` | Tokens da Organização ativa: nome, Integração, prefixo, uso e revogação, sem o segredo |
| `POST /api/v1/ingestion-tokens` | `{ "name": "SAP PI produção", "integration_id": "uuid" }` → `201 { id, token, prefix }` |
| `POST /api/v1/ingestion-tokens/{id}/revoke` | Revoga → `204`; repetir não muda a data |

O `token` (`aid_ing_…`) aparece **uma vez**, na criação. O banco guarda o sha256, e a tela mostra só o prefixo. Cada token é preso a uma Integração: Integração arquivada fecha o token.

## POST /api/v1/ingestion/events

```http
POST /api/v1/ingestion/events
Authorization: Bearer aid_ing_…
Content-Type: application/json

{ "events": [ { "schema_version": "1.0", "event_id": "<UUIDv7>", "integration_id": "<a do token>", … } ] }
```

→ `202 { "accepted": 1, "rejected": [ { "index": 1, "reason": "fora do Contrato de evento: $.severity" } ] }`

- **Limites:** até 500 Eventos e 1 MB por lote. Acima disso, `413 batch_too_large`.
- **Tenant:** vem do token. Qualquer Evento com `tenant_id` recusa o lote inteiro com `422 tenant_id_not_allowed`.
- **Rejeição por item:** Evento fora do contrato, ou com `integration_id` diferente do token, é rejeitado individualmente. O motivo traz só os caminhos dos campos, nunca os valores.
- **Processamento:** os aceitos viram um lote (`doctor.ingestion_batches`) com uma mensagem `ingestion.raw` na outbox, na mesma transação. O worker de ingestão sanitiza e grava `doctor.events`.
- **Repetição:** pode reenviar o mesmo lote à vontade. A deduplicação usa tenant, fonte e `event_id`, então o mesmo Evento enviado 3 vezes fica uma vez só.
- **Rate limit:** por token, `429` com `Retry-After`.

A API não usa `service_role` aqui: as funções do token (`doctor.resolve_ingestion_token` e `doctor.accept_ingestion_batch`) rodam como `anon` e são as únicas que `anon` executa no schema `doctor`. Há teste no pgTAP para isso.

## Erros (`application/problem+json`)

| Status | `code` | Quando |
|---|---|---|
| 401 | `invalid_ingestion_token` | Token ausente, desconhecido, revogado, de Integração arquivada ou de Organização inativa |
| 403 | `forbidden`, `mfa_required` | Gestão de tokens sem Owner/Admin com MFA |
| 404 | `not_found` | Integração ou token de outra Organização |
| 413 | `batch_too_large` | Mais de 500 Eventos ou de 1 MB |
| 422 | `tenant_id_not_allowed` | Algum Evento traz `tenant_id` |
| 422 | `validation_error` | Corpo que não é `{"events": [...]}` |
| 429 | `rate_limited` | Muitas requisições do mesmo token |
