# Agentes locais

Ticket #39, [ADR-0015](../adr/0015-agente-local-so-de-saida.md). Instalação: [docs/operations/agente.md](../operations/agente.md).

## Gestão (tela de agentes)

Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. Todo Papel lê; criar, configurar, renovar e revogar exigem Owner ou Admin com `aal2`. As rotas que mudam algo aceitam `Idempotency-Key`: repetir o `POST` com a mesma chave devolve o mesmo token, sem emitir outro.

| Rota | Efeito |
|---|---|
| `GET /api/v1/agents` | Agentes da Organização ativa: `status` (`pending`, `active`, `revoked`), `version`, `last_seen_at`, `config`, `cert_fingerprint`, `registration_expires_at` |
| `POST /api/v1/agents` | `{ name, integration_id, config? }` → `201` com `{ id, registration_token, expires_in_hours, install_command }` |
| `PATCH /api/v1/agents/{id}` | `{ config }` → `{ config_version }`; o agente recebe no próximo long-poll |
| `POST /api/v1/agents/{id}/rotate` | Corta o segredo e a chave atuais e emite um token novo → mesmo formato do `POST` |
| `POST /api/v1/agents/{id}/revoke` | Recusa a próxima requisição do agente → `204` |

- O **token de registro** aparece só na resposta: vale 24 h e um registro. O banco guarda só o hash.
- **Config** (`422 invalid_config` com a regra quebrada, nunca o valor):

```json
{
  "interval_seconds": 300,
  "collections": [
    { "type": "directory", "path": "/exports/sap", "pattern": "*.csv", "format": "csv" },
    { "type": "rfc_table", "table": "EDIDS", "max_rows": 1000 },
    { "type": "rfc_function", "name": "Z_AID_READ_SLG1" }
  ]
}
```

  `directory`: caminho absoluto, sem `..`; `format` `csv`, `ndjson` ou `json`. `rfc_table`: só `EDIDC` e `EDIDS`, campos dentro da allowlist (padrão: todos os da allowlist), sempre com os campos de id, status, data e hora (`EDIDS`: `DOCNUM`, `COUNTR`, `STATUS`, `LOGDAT`, `LOGTIM`; `EDIDC`: `DOCNUM`, `STATUS`, `UPDDAT`, `UPDTIM`). `rfc_function`: só `Z_AID_…`. Até 10 coletas; `interval_seconds` de 60 a 3600.

## Rotas do agente

Sem sessão de Usuário. Fora o registro, toda chamada leva:

| Cabeçalho | Valor |
|---|---|
| `Authorization` | `Bearer aid_agt_…` (devolvido no registro) |
| `X-AID-Timestamp` | segundos Unix; recusado fora de ±5 min |
| `X-AID-Signature` | base64 da assinatura Ed25519 de `"{MÉTODO}\n{caminho[?query]}\n{timestamp}\n{sha256 hex do corpo}"`; a query entra exatamente como vai na URL |

| Rota | Efeito |
|---|---|
| `POST /api/v1/agent/register` | `{ token, public_key, version }` (`public_key`: 32 bytes Ed25519 em base64) → `201 { agent_id, secret, certificate }`; `401 invalid_registration` se o token já foi usado ou venceu |
| `GET /api/v1/agent/config?known_version=N&version=X` | Sinal de vida (grava `last_seen_at` e a versão) e long-poll de até 25 s: `200 { integration_id, config, config_version, update }` quando a versão mudou, `304` se não |
| `POST /api/v1/agent/events` | `{ events: [...] }` no Contrato v1, mesmos limites de `POST /ingestion/events` (500 Eventos, 1 MB) → `202 { accepted, rejected }` |

- Agente revogado, segredo errado ou assinatura inválida: `401 invalid_agent`.
- Corpo acima de 1 MB em `/events` (4 KB nas outras): `413 batch_too_large`, recusado sem ler o resto. O agente divide o lote; um lote recusado por inteiro de outro jeito vai para a quarentena local (`rejected` em `buffer.sqlite3`).
- Cota de Eventos esgotada: `429 quota_exceeded`. O agente mantém a fila e tenta na próxima rodada.
- `update` (quando a plataforma tem `AID_AGENT_RELEASE`): `{ version, url, sha256, signature }`, com a assinatura Ed25519 de `"{version}\n{sha256}\n{url}"` pela chave de release.

## Modelo local (#46)

| Rota | Efeito |
|---|---|
| `GET /api/v1/agent/llm` | Long-poll (até 25 s) do próximo pedido ao modelo local da Organização: `200 { id, request, timeout_seconds }` (o corpo de um chat completion, já sanitizado, e o prazo da resposta) ou `204` |
| `POST /api/v1/agent/llm/{id}` | `{ "response": {...} }` (a resposta do servidor local) ou `{ "error": "..." }`. `204`; `404` se o pedido não é deste agente ou já foi respondido |

As duas rotas são assinadas como as outras do agente. O bloco `llm` da config (`base_url` `http(s)://servidor[:porta]/v1`) diz para onde o agente leva os pedidos. Operação em [docs/operations/ia-local.md](../operations/ia-local.md).
