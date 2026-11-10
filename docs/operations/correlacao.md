# Correlação de Execuções

O worker `correlation` (mesma imagem dos workers, `WORKER_NAME=correlation`) transforma Eventos em Execuções. O motor é `packages/correlation`, puro e determinístico (README do pacote); a decisão de nunca dividir Execuções está na ADR-0012.

## Fluxo

1. A ingestão grava os Eventos e, na mesma transação, `correlation.requested` com a `integration_id` na outbox.
2. O worker pega até 2.000 Eventos pendentes da Integração (`execution_ref` nulo), a vizinhança já correlacionada e os demais Eventos dessas Execuções, e roda o motor. A Organização sai da Integração, nunca da mensagem.
3. Cada grupo vira uma Execução nova, a que já existia, ou a mais antiga entre as que ele junta. As outras ficam marcadas `merged_into`, fechadas e sem Eventos, com histórico em `execution_merges`; nada é apagado. Os pendentes recebem `execution_ref` e `correlated_by`; a Execução recebe contagem, duração, chaves e status (`failed` com erro, senão `pending_confirmation`).
4. Com mais de 2.000 pendentes, o worker põe outro `correlation.requested` na outbox e continua na próxima mensagem.

Um lock por Integração (`pg_advisory_xact_lock`) serializa mensagens da mesma Integração. Mensagem repetida não acha pendentes e termina sem efeito.

## Correlação entre sistemas (ticket #40)

Um pedido criado no Salesforce, processado no Cloud Run e com timeout no SAP tem um id forte diferente em cada sistema. O **Mapa de identificadores** da Integração (`doctor.correlation_mappings`, API em [docs/api/correlation.md](../api/correlation.md)) diz onde cada sistema guarda a mesma chave de negócio e como normalizá-la:

```json
[
  { "system": "salesforce", "field": "execution_id" },
  { "system": "gcp", "field": "attributes.sf_order", "transforms": [{ "op": "strip_prefix", "value": "SF-" }] },
  { "system": "sap", "field": "attributes.bstkd", "transforms": [{ "op": "strip_leading_zeros" }] }
]
```

- `system` é o `source.provider` do Evento; `field` é `execution_id`, `trace_id` ou `attributes.<nome>` (até dois níveis): só campos que identificam um registro. Operação, recurso e código de erro se repetem entre pedidos e juntariam Execuções sem relação.
- Transformações, em ordem: `trim`, `upper`, `lower`, `strip_leading_zeros`, `strip_prefix` e `strip_suffix` (com `value`).
- O worker calcula as chaves dos pendentes (`<id do Mapa>:<valor>`), grava em `events.cross_keys` (índice GIN) e busca os vizinhos já correlacionados com a mesma chave na janela do Mapa (`window_minutes`, padrão 60). A janela é fixa a partir do primeiro Evento com a chave: uma chave que se repete a cada 50 min não encadeia Execuções de um dia. Evento com a chave e sem par continua solto, e a Referência ou a proximidade ainda podem prendê-lo.
- A estratégia `cross_system` fica entre `trace_id` e a Referência de negócio. Ela junta grupos com ids fortes diferentes, porque o Mapa é a Organização dizendo que são o mesmo fluxo. Evento com id forte continua marcado pelo id forte; só o que entrou pela chave fica `cross_system`.
- Mudar um Mapa vale para os Eventos que chegarem depois: os já correlacionados guardam as chaves calculadas na hora.
- A Timeline mostra uma raia por sistema quando a Execução passa por mais de um.
- **Tela:** Integrações → **Mapa entre sistemas**. Todo Papel vê; Owner e Admin com MFA cadastram (até três chaves, com prefixo, zeros à esquerda e maiúsculas, janela, divergência e a consulta no destino) e removem.

## Fechamento

O Cloud Scheduler chama `POST /close` a cada minuto (`aid-correlation-close`). Execução sem mudança há 5 min fecha:

| Situação | Status final |
|---|---|
| algum Evento `ERROR` ou `CRITICAL` | `failed` |
| agrupada por proximidade temporal, ou sem estratégia | `unknown` |
| o resto | `success` |

Cada Execução fechada põe `rules.evaluate` (`execution_id`, `integration_id`) na outbox, consumido pelo worker `diagnosis` (Regras e Incidentes, `docs/operations/regras.md`).

## Agregado do Dashboard

O Cloud Scheduler chama `POST /stats` a cada 10 min (`aid-dashboard-stats`): `doctor.refresh_execution_stats` drena a fila de horas que os triggers anotaram e as recalcula (`docs/api/dashboard.md`).
