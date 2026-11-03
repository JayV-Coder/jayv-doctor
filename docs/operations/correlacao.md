# Correlação de Execuções

O worker `correlation` (mesma imagem dos workers, `WORKER_NAME=correlation`) transforma Eventos em Execuções. O motor é `packages/correlation`, puro e determinístico (README do pacote); a decisão de nunca dividir Execuções está na ADR-0012.

## Fluxo

1. A ingestão grava os Eventos e, na mesma transação, `correlation.requested` com a `integration_id` na outbox.
2. O worker pega até 2.000 Eventos pendentes da Integração (`execution_ref` nulo), a vizinhança já correlacionada e os demais Eventos dessas Execuções, e roda o motor. A Organização sai da Integração, nunca da mensagem.
3. Cada grupo vira uma Execução nova, a que já existia, ou a mais antiga entre as que ele junta (fusão em `execution_merges`). Os pendentes recebem `execution_ref` e `correlated_by`; a Execução recebe contagem, duração, chaves e status (`failed` com erro, senão `pending_confirmation`).
4. Com mais de 2.000 pendentes, o worker põe outro `correlation.requested` na outbox e continua na próxima mensagem.

Um lock por Integração (`pg_advisory_xact_lock`) serializa mensagens da mesma Integração. Mensagem repetida não acha pendentes e termina sem efeito.

## Fechamento

O Cloud Scheduler chama `POST /close` a cada minuto (`aid-correlation-close`). Execução sem mudança há 5 min fecha:

| Situação | Status final |
|---|---|
| algum Evento `ERROR` ou `CRITICAL` | `failed` |
| agrupada por proximidade temporal, ou sem estratégia | `unknown` |
| o resto | `success` |

Cada Execução fechada põe `rules.evaluate` (`execution_id`, `integration_id`) na outbox. O tópico e o worker das Regras chegam com o ticket #18; até lá o relay tenta publicar e conta as tentativas.
