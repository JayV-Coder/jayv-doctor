# Enriquecimento sob demanda pelo worker de Conectores, com o Diagnóstico esperando na fila

Depois de um timeout, a pergunta que decide a Recomendação é "o pedido existe no destino?". O #40 pede essa consulta na etapa 2 do Diagnóstico. Quem roda o Diagnóstico é o worker de diagnóstico, mas as credenciais dos clientes ficam no Vault, e só o worker de Conectores as lê (ADR-0006). Dar ao worker de diagnóstico acesso às credenciais aumentaria o alcance de um vazamento: é o worker que fala com o LLM.

Então a consulta é um pedido entre workers:

1. O worker de diagnóstico, na etapa 2, olha os Mapas da Integração com `lookup` e as chaves das Execuções do Incidente. Grava até 5 consultas `pending` em `doctor.enrichments`, põe `enrichment.requested` na outbox e devolve o Diagnóstico à fila (`queued`, etapa `correlation`), sem contar a passagem como tentativa.
2. O worker de Conectores lê a credencial, consulta só para leitura (SOQL `SELECT … LIMIT 1` no Salesforce, `$filter … $top=1` no OData), grava `found`, `not_found` ou `failed` com a mensagem classificada do Conector e põe `diagnosis.requested` na outbox.
3. O worker de diagnóstico retoma. A consulta vira Evidência do tipo `enrichment`, apontando para o registro em `doctor.enrichments` da mesma Organização. Encontrado o pedido, a primeira Recomendação passa a ser "não reenviar", e as que sugerem reprocessar saem, nos dois modos e depois do LLM.

Sem resposta em 5 min, a rota agendada `POST /enrichment/expire` marca a consulta como `failed` e pede o Diagnóstico de novo. Ele segue com uma nota de verificação, e uma consulta perdida não prende o Diagnóstico.

## Consequências

- O worker de diagnóstico continua sem credencial de cliente; o de Conectores ganha um tópico.
- O Diagnóstico com consulta demora uma ida e volta pela outbox a mais, de segundos, ou até 5 min se o Conector não responder.
- A Evidência da consulta não tem link na tela: o registro está no sistema do cliente. O texto diz o que foi consultado, o resultado e quando.
- O Conector OData é só de consulta: o agendador não pede Sincronização para ele. O host do serviço precisa resolver só para endereços públicos. A conferência acontece na própria conexão: o transporte resolve o nome, confere e conecta no endereço conferido, com o TLS validando o nome original. Um DNS que muda de resposta (rebinding) não leva à rede interna. Também é obrigatório HTTPS e não há redirecionamento.
- A Recomendação muda só quando a consulta foi no destino da Integração e o Incidente é de categoria com risco de reenvio (timeout, conectividade, confirmação pendente, desconhecida). Nos outros casos, a consulta entra só como Evidência.
- O Diagnóstico que fica na fila com as consultas já respondidas (a resposta chegou antes de ele voltar à fila, ou o pedido de retomada se perdeu) é pedido de novo pela mesma rota agendada.
