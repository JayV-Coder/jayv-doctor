# aid-correlation

Agrupa Eventos de uma Organização em Execuções (ticket #17), sem banco nem rede: o worker
`correlation` carrega os Eventos, chama `Correlator.correlate` e grava o resultado.

Estratégias, da mais forte para a mais fraca (`correlated_by` de cada Evento):

1. `execution_id` igual dentro da Integração;
2. `trace_id` igual (também dentro da Integração);
3. `business_reference`: Evento sem `execution_id` nem `trace_id` com a mesma Referência de
   negócio, `operation` compatível e até 15 min de distância;
4. `temporal_proximity`: até 2 s, mesmo `source.resource` e `attributes.attempt` seguido. É
   fraca: a Execução fica marcada `low_confidence`.

O resultado depende só do conjunto de Eventos, nunca da ordem de chegada.
