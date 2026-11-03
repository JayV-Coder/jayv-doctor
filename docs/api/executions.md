# Execuções e Eventos

Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. Todo Papel lê; o Log bruto é de Analyst para cima.

| Rota | Efeito |
|---|---|
| `POST /api/v1/executions/search` | Lista paginada (50 por página, mais recentes primeiro) com filtros no corpo |
| `GET /api/v1/executions/{id}` | Metadados, Eventos em ordem, `correlated_by`, Regras que dispararam e Incidente |
| `GET /api/v1/events/{id}` | Evento normalizado (já sanitizado), resumo da Sanitização e origem |
| `GET /api/v1/raw-logs/{id}/download` | URL assinada de 5 min para o Log bruto; auditado |

## Busca

```json
{ "q": "4500012345", "integration_id": "…", "environment": "prd", "status": "failed",
  "from": "2026-11-02T00:00:00Z", "to": "2026-11-02T23:59:59Z", "cursor": "…", "limit": 50 }
```

- **Por que POST:** o termo pode ser um número de pedido. Na URL de um GET ele iria para os logs do Cloud Run e do balanceador; no corpo, não.
- `q` acha a Execução por `execution_id`, `trace_id`, id da Execução ou **Referência de negócio**. A Referência vira `hmac:` com a chave da Organização (HKDF da `HMAC_MASTER_KEY`) no servidor, como na ingestão: o número digitado nunca chega ao banco nem aos logs. Sem `HMAC_MASTER_KEY`, a busca fica só nos ids técnicos.
- `from`/`to` filtram Execuções que tocam o intervalo. `next_cursor` traz a próxima página; cursor inválido responde `422 invalid_cursor`.
- Execuções fundidas em outra (correlação, ADR-0012) não aparecem na lista; o detalhe de uma delas mostra a sobrevivente.

## Detalhe

Cada Evento da Timeline traz `rule_codes`: as Regras cujo match aponta aquele Evento como prova. `rules` lista as Regras com versão, categoria e descrição.

## Evento e Log bruto

- `sanitization_report` é `{ "counts": { "bearer": 1, … }, "truncated": false }`.
- `raw_log` (id, origem, vencimento e dias restantes de retenção, nome do arquivo importado) só vem para Analyst ou acima, como o próprio bucket.
- O download confere o Papel na tabela, registra a auditoria (`raw_log.downloaded` em `doctor.audit_logs`, na mesma transação da assinatura: se o Storage falhar, nada fica registrado) e assina a URL no Storage com o JWT do Usuário: a política do bucket repete a regra. Log vencido responde `404`.

## Erros (`application/problem+json`)

| Status | `code` | Quando |
|---|---|---|
| 403 | `forbidden` | Viewer pedindo o Log bruto |
| 404 | `not_found` | Execução, Evento ou Log bruto inexistente nesta Organização (ou vencido) |
| 422 | `invalid_cursor`, `validation_error` | Cursor ou filtros inválidos |
