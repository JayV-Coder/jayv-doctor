# Correlação incremental: Execuções só se juntam, nunca se dividem

O ticket #17 pede correlação determinística: a mesma entrada produz a mesma saída, em qualquer ordem de chegada. Os Eventos, porém, chegam em lotes, e as Execuções já gravadas têm id, aparecem na tela e logo terão Incidentes e Evidências apontando para elas. Recalcular tudo do zero a cada lote mudaria esses ids.

Por isso o worker roda o motor (`packages/correlation`) sobre os Eventos pendentes, a vizinhança que pode se ligar a eles e todos os Eventos das Execuções envolvidas. A Execução já gravada entra como ligação forte (`execution_ref`): os Eventos dela ficam sempre no mesmo grupo. Quando o grupo junta duas Execuções (por exemplo, o `trace_id` chega depois), a de primeiro Evento mais antigo fica com tudo, e a outra vai para `execution_merges` com as chaves que tinha.

## Consequências

- O resultado de um lote é determinístico: o motor decide pelo conjunto, com desempates por (instante, id). Uma Execução que, com todos os Eventos à vista desde o início, teria sido dividida em duas continua uma só, se a ligação fraca veio antes.
- As estratégias fracas (Referência, proximidade) só prendem Eventos sem `execution_id` nem `trace_id`, e nunca juntam dois grupos de ids fortes diferentes. Isso limita a fusão errada que o "nunca dividir" tornaria permanente.
- O fechamento conta 5 min a partir da última mudança feita pela correlação (`last_activity_at`), não do instante dos Eventos, que numa Importação podem ser de dias atrás. Evento tardio reabre a Execução, que fecha de novo e pede as Regras outra vez.
