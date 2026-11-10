# Mapas de identificadores

Ticket #40. Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. Todo Papel lê; criar, alterar e remover exigem Owner ou Admin com `aal2`. As rotas que mudam algo aceitam `Idempotency-Key`. Como o Mapa é usado está em [docs/operations/correlacao.md](../operations/correlacao.md).

| Rota | Efeito |
|---|---|
| `GET /api/v1/integrations/{id}/correlation-mappings` | Mapas da Integração |
| `POST /api/v1/integrations/{id}/correlation-mappings` | `{ name, keys, window_minutes?, reconcile?, lookup? }` → `201` |
| `PATCH /api/v1/correlation-mappings/{id}` | qualquer campo; `clear_lookup: true` tira a consulta |
| `DELETE /api/v1/correlation-mappings/{id}` | `204` |

- **`keys`**: de 1 a 6 itens `{ system, field, transforms? }`. Inválido: `422 invalid_mapping`, com o item e a regra.
- **`window_minutes`**: de 1 a 1.440 (padrão 60). Mesma chave fora da janela não une.
- **`reconcile`**: liga a detecção de divergência (INT-008) entre origem e destino da Integração.
- **`lookup`**: consulta de leitura feita no Diagnóstico (enriquecimento, [ADR-0016](../adr/0016-enriquecimento-pelo-worker-de-conectores.md)):

```json
{
  "connector_id": "…",
  "entity": "A_SalesOrder",
  "field": "PurchaseOrderByCustomer",
  "status_field": "OverallSDProcessStatus",
  "pad_left": 0
}
```

  O Conector precisa ser desta Organização e de um provedor que consulta (`salesforce` ou `odata`). `entity`, `field` e `status_field` seguem o padrão de identificador; `pad_left` devolve os zeros que o destino guarda (o VBELN tem 10 dígitos).
- Nome repetido na mesma Integração: `409 mapping_exists`.
