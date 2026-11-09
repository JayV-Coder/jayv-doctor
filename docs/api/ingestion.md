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
- **Rejeição por item:** Evento fora do contrato, com `integration_id` diferente do token ou com `timestamp` fora da janela (de 2000 até amanhã) é rejeitado individualmente. O motivo traz só os caminhos dos campos, nunca os valores.
- **Processamento:** os aceitos viram um lote (`doctor.ingestion_batches`) com uma mensagem `ingestion.raw` na outbox, na mesma transação. O worker de ingestão sanitiza e revalida cada Evento antes de gravar `doctor.events`:
  - a sanitização cobre também `execution_id`, `trace_id` e `source`, que vêm do cliente;
  - Evento que sai do contrato depois da sanitização é descartado e contado em `skipped`;
  - erro permanente fica registrado no lote (`failed_at`, `error`).
- **Repetição:** pode reenviar o mesmo lote à vontade. A deduplicação usa tenant, Integração, fonte e `event_id`, então o mesmo Evento enviado 3 vezes fica uma vez só.
- **Rate limit:** por token, contado só depois de o token ser validado, com `429` e `Retry-After`. O corpo só é lido depois do token, e sem passar de 1 MB na memória.

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

## Exemplos

O `event_id` é um **UUIDv7 gerado uma vez por Evento, na origem**. Reenviar o mesmo Evento (depois de um timeout, por exemplo) usa o mesmo id, e a deduplicação o descarta. Agrupe até 500 Eventos por lote; respeite o `Retry-After` do `429` e tente de novo nos `5xx`, com espera crescente.

### curl

```bash
curl -sS https://api.<domínio>/api/v1/ingestion/events \
  -H "Authorization: Bearer $AID_INGESTION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "schema_version": "1.0",
      "event_id": "0192e1c4-7b2c-7d4e-8f00-123456789abc",
      "integration_id": "'"$AID_INTEGRATION_ID"'",
      "execution_id": "pedido-12345-tentativa-1",
      "timestamp": "2026-11-10T14:05:00Z",
      "source": {"provider": "sap", "service": "PI"},
      "operation": "BAPI_SALESORDER_CREATEFROMDAT2",
      "severity": "ERROR",
      "error": {"category": "TIMEOUT", "http_status": 504, "message": "UPSTREAM_TIMEOUT"}
    }]
  }'
```

### Python (httpx)

```python
import os
import time
import uuid

import httpx

URL = "https://api.<domínio>/api/v1/ingestion/events"
HEADERS = {"Authorization": f"Bearer {os.environ['AID_INGESTION_TOKEN']}"}


def uuid7() -> str:
    ms = time.time_ns() // 1_000_000
    value = (ms << 80) | int.from_bytes(os.urandom(10), "big")
    value = (value & ~(0xF << 76)) | (0x7 << 76)
    value = (value & ~(0x3 << 62)) | (0x2 << 62)
    return str(uuid.UUID(int=value))


def wait(response: httpx.Response | None, attempt: int) -> float:
    """Retry-After em segundos quando vier; senão espera crescente (1, 2, 4… s)."""
    header = response.headers.get("Retry-After", "") if response is not None else ""
    return float(header) if header.isdigit() else float(2**attempt)


def send(events: list[dict], attempts: int = 5) -> dict:
    for attempt in range(attempts):
        try:
            response = httpx.post(URL, json={"events": events}, headers=HEADERS, timeout=30)
        except httpx.TransportError:
            response = None  # rede ou timeout: tente de novo, o event_id evita duplicar
        else:
            if response.status_code == 202:
                return response.json()  # {"accepted": n, "rejected": [{"index", "reason"}]}
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()  # 4xx: lote inválido, não adianta repetir
        if attempt < attempts - 1:
            time.sleep(wait(response, attempt))
    raise RuntimeError("ingestão indisponível")
```

Gere o `event_id` (com `uuid7()`) ao **criar** o Evento e guarde-o junto, não a cada envio.

### Node (fetch, Node 20+)

```js
const URL = "https://api.<domínio>/api/v1/ingestion/events";

export async function send(events, attempts = 5) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    let response = null;
    try {
      response = await fetch(URL, {
        method: "POST",
        headers: {
          authorization: `Bearer ${process.env.AID_INGESTION_TOKEN}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ events }),
        signal: AbortSignal.timeout(30_000),
      });
    } catch {
      // Rede ou timeout: tente de novo; o event_id evita duplicar.
    }
    if (response?.status === 202) return response.json(); // { accepted, rejected }
    if (response && response.status !== 429 && response.status < 500) {
      throw new Error(`lote recusado: ${response.status}`); // 4xx: não repita igual
    }
    if (attempt < attempts - 1) {
      const header = response?.headers.get("retry-after") ?? "";
      const seconds = /^\d+$/.test(header) ? Number(header) : 2 ** attempt;
      await new Promise((resolve) => setTimeout(resolve, seconds * 1000));
    }
  }
  throw new Error("ingestão indisponível");
}
```

O contrato completo do Evento está em `packages/contracts/schemas/event.v1.json`, e a especificação da API, em [OpenAPI](README.md).
