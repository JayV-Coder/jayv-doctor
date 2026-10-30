# Contratos (`@aid/contracts` · `aid-contracts`)

Fonte única dos formatos trocados entre fontes, API, workers e web. Hoje: o **Contrato de evento v1** ([`schemas/event.v1.json`](schemas/event.v1.json)), formato canônico de todo Evento normalizado.

| Artefato | Origem |
|---|---|
| `schemas/event.v1.json` | **editado à mão** (JSON Schema 2020-12) |
| `python/aid_contracts/event_v1.py`, `python/aid_contracts/schemas/` | gerado (`datamodel-codegen`) |
| `src/generated/event.v1.ts` | gerado (`json-schema-to-typescript`) |

Depois de editar um schema, rode `make contracts`. O CI regenera e falha se o resultado divergir do commitado.

## Uso

```python
from aid_contracts import EventValidationError, validate_event

event = validate_event(payload)  # EventV1 tipado, ou EventValidationError(.errors)
```

```ts
import { validateEvent } from "@aid/contracts";

const result = validateEvent(payload); // { ok: true, event } | { ok: false, errors }
```

Os dois lados validam contra o mesmo JSON Schema (jsonschema em Python, Ajv em TS) e compartilham as fixtures de `fixtures/event.v1/{valid,invalid}`, então aceitam e rejeitam os mesmos payloads.

## Regras do contrato

- `tenant_id` nunca é aceito no payload. O tenant vem da identidade autenticada do Conector ou do token de ingestão (ADR-0004).
- `event_id` é UUIDv7. `timestamp` é RFC 3339 com fuso e no máximo microssegundos.
- `attributes` é plano: até 64 chaves `snake_case` (≤ 40 caracteres), com valores string (≤ 200), número, booleano ou nulo. Esses limites mantêm o bloco abaixo de 16 KB sem uma checagem extra de tamanho.
- `business_context.entity_reference` é persistida como `hmac:<hex>` depois da Sanitização (ticket #13).

## Versionamento

- **Minor** (`1.0` → `1.1`): mudança compatível, como campo opcional novo ou valor de enum novo. Edite `event.v1.json` e aceite `1.x` em `schema_version`.
- **Major**: mudança incompatível (campo removido ou obrigatório novo, tipo alterado). Crie `event.v2.json` ao lado do v1. O v1 continua aceito por 2 releases após o v2 entrar em produção.
