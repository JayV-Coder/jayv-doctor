# Webhooks de saída

Ticket #42. Só Owner e Admin com `aal2`. Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa; as rotas que mudam algo aceitam `Idempotency-Key`. Quem entrega é o worker `notifier` ([ADR-0017](../adr/0017-alertas-por-worker-proprio.md)).

| Rota | Efeito |
|---|---|
| `GET /api/v1/webhooks` | Webhooks da Organização, sem o segredo |
| `POST /api/v1/webhooks` | `{ name, url, events }` → `201 { id, secret }` (o segredo aparece só aqui; a repetição com a mesma `Idempotency-Key` devolve `"[exibido uma vez]"`) |
| `PATCH /api/v1/webhooks/{id}` | `url`, `events` e/ou `enabled` (religar zera as falhas) |
| `POST /api/v1/webhooks/{id}/rotate-secret` | Segredo novo → `{ id, secret }`; o anterior deixa de valer na hora |
| `DELETE /api/v1/webhooks/{id}` | Remove o webhook e o segredo do Vault → `204` |
| `GET /api/v1/webhooks/{id}/deliveries` | As 50 entregas mais recentes: status, tentativas, HTTP, latência, até 1 KB da resposta, corpo |
| `POST /api/v1/webhook-deliveries/{id}/resend` | Reenvia o mesmo corpo numa entrega nova → `202 { id }` |

- **Eventos**: `incident.opened`, `incident.updated` (status, severidade, responsável ou título; a contagem de Execuções não conta), `incident.resolved`, `diagnosis.published`, `diagnosis.reviewed`.
- **Endereço** (`422 unsafe_url`): só HTTPS, sem usuário na URL; o host não pode ser IP privado, local ou de metadados (`169.254.169.254`), nem nome de rede interna (`localhost`, `*.internal`, `metadata…`), nem resolver para um deles. Na entrega, a conexão vai para o endereço conferido naquela hora, sem seguir redirecionamento.
- **Entrega**: 2xx em até 15 s (prazo total; só o primeiro 1 KB da resposta é lido) é sucesso. O resto tenta de novo com espera de 1, 2, 4… até 60 min, por até 24 h; depois, `abandoned`. Com 50 falhas seguidas, o webhook desliga e os Owners e Admins recebem um e-mail.

## Payload `webhook.v1`

Só ids, títulos e links, nunca Eventos brutos nem dados de log. O conteúdo é o retrato da hora do evento: um Incidente resolvido logo depois de aberto chega no `incident.opened` como aberto.

```json
{
  "version": "webhook.v1",
  "id": "0d9c…",
  "event": "incident.opened",
  "created_at": "2026-11-10T14:02:31+00:00",
  "organization_id": "4a1f…",
  "data": {
    "incident": {
      "id": "7b2e…",
      "number": 123,
      "title": "Timeout na criação de pedidos",
      "severity": "critical",
      "status": "open",
      "category": "TIMEOUT",
      "environment": "prd",
      "integration": { "id": "…", "name": "Pedidos Salesforce → SAP" },
      "url": "https://app.exemplo.com/incidentes/7b2e…"
    }
  }
}
```

`diagnosis.published` e `diagnosis.reviewed` trazem `data.diagnosis` (`id`, `incident_id`, `version`, `status`, `classification`, `confidence_heuristic`, `requires_human_review`, `url`); o segundo traz também `data.review.verdict`. O `id` é o mesmo nas novas tentativas e no "Reenviar": use-o para não processar duas vezes.

## Cabeçalhos e assinatura

| Cabeçalho | Valor |
|---|---|
| `X-AID-Event` | o evento |
| `X-AID-Delivery` | o id desta entrega (muda no "Reenviar") |
| `X-AID-Signature` | `t=<segundos Unix>,v1=<hex>`, com `v1 = HMAC-SHA256(segredo, "<t>.<corpo>")` |

Confira a assinatura com o **corpo exato** que chegou (antes de interpretar o JSON) e recuse `t` com mais de 5 min de diferença (anti-replay). Os dois exemplos abaixo rodam no teste automatizado `packages/alerts/tests/test_docs_webhooks.py`.

Python:

```python
import hashlib
import hmac
import time


def verify(secret: str, header: str, body: bytes, tolerance: int = 300) -> bool:
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    try:
        timestamp = int(parts["t"])
    except (KeyError, ValueError):
        return False
    if abs(time.time() - timestamp) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return hmac.compare_digest(expected.hexdigest(), parts.get("v1", ""))
```

Node:

```js
const crypto = require("node:crypto");

function verify(secret, header, body, tolerance = 300) {
  const parts = Object.fromEntries(
    header.split(",").map((item) => item.split("=", 2)).filter((pair) => pair.length === 2),
  );
  const timestamp = Number.parseInt(parts.t, 10);
  if (!Number.isFinite(timestamp)) return false;
  if (Math.abs(Date.now() / 1000 - timestamp) > tolerance) return false;
  const expected = crypto
    .createHmac("sha256", secret)
    .update(`${timestamp}.`)
    .update(body)
    .digest("hex");
  const given = Buffer.from(parts.v1 ?? "", "utf8");
  const wanted = Buffer.from(expected, "utf8");
  return given.length === wanted.length && crypto.timingSafeEqual(given, wanted);
}
```

No Express, leia o corpo cru (`express.raw({ type: "application/json" })`) e passe o `Buffer` para `verify`.
