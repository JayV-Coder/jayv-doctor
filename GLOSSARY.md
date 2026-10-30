# Integration AI Doctor

Plataforma SaaS B2B que coleta, correlaciona e diagnostica falhas em integrações corporativas (SAP, Salesforce, Google Cloud), apresentando causas prováveis com evidências verificáveis.

## Organização e acesso

**Organização**:
Cliente do SaaS; a unidade de isolamento de dados. No código e no banco é chamada de `tenant`.
_Avoid_: Conta, empresa, cliente, workspace

**Usuário**:
Pessoa autenticada que pode pertencer a várias Organizações.
_Avoid_: Conta, login

**Vínculo**:
Relação entre um Usuário e uma Organização, com exatamente um Papel.
_Avoid_: Membership (em texto de produto), associação

**Papel**:
Conjunto fixo de permissões de um Vínculo: Owner, Admin, Analyst ou Viewer.
_Avoid_: Perfil, permissão, grupo

**Organização ativa**:
A Organização em cujo contexto o Usuário está operando no momento; toda leitura e escrita acontece dentro dela.
_Avoid_: Tenant atual, contexto

**Convite**:
Oferta pendente para um e-mail ingressar em uma Organização com um Papel definido.

**Cota**:
Limite de uso de um recurso (eventos ingeridos, Diagnósticos, armazenamento) por Organização e período.
_Avoid_: Limite, franquia

## Fontes e coleta

**Integração**:
Fluxo de negócio monitorado entre um sistema de origem e um de destino, em um Ambiente (ex.: "Pedidos Salesforce → SAP, produção").
_Avoid_: Interface, fluxo, pipeline

**Ambiente**:
Estágio de uma Integração: desenvolvimento, homologação ou produção.
_Avoid_: Stage, tier

**Conector**:
Configuração autenticada que coleta registros de um provedor (GCP, Salesforce, SAP) para uma Organização.
_Avoid_: Integração (é outra coisa), fonte, plugin

**Sincronização**:
Uma rodada de coleta de um Conector, delimitada por um Checkpoint inicial e final.
_Avoid_: Sync job, pull

**Checkpoint**:
Marca persistida até onde um Conector já coletou, para retomar sem perda nem duplicação.
_Avoid_: Cursor, offset

**Importação manual**:
Envio de um arquivo de logs (JSON/CSV) pelo Usuário, sem Conector.
_Avoid_: Upload

**Log bruto**:
Registro original como recebido da fonte, guardado sem interpretação e por prazo curto.
_Avoid_: Payload, raw

**Evento**:
Registro normalizado no Contrato de evento, derivado de um Log bruto.
_Avoid_: Log, mensagem, entrada

**Contrato de evento**:
Formato canônico e versionado que todo Evento obedece, independentemente da fonte.
_Avoid_: Schema, envelope

**Referência de negócio**:
Identificador comercial (pedido, cliente, nota) transformado em HMAC por Organização, que permite correlacionar sem expor o valor.
_Avoid_: Business key, ID mascarado

**Sanitização**:
Remoção de segredos e dados pessoais de um registro antes de ele ser persistido como Evento ou enviado a um modelo de IA.
_Avoid_: Mascaramento, limpeza

## Investigação

**Execução**:
Uma ocorrência de uma Integração, reconstruída pela Correlação de seus Eventos.
_Avoid_: Run, job, transação

**Correlação**:
Associação de Eventos à mesma Execução por identificadores técnicos, Referências de negócio e proximidade temporal.
_Avoid_: Agrupamento, matching

**Timeline**:
Sequência temporal dos Eventos de uma Execução.

**Incidente**:
Falha ou anomalia de uma Execução que merece investigação; tem categoria, severidade e status.
_Avoid_: Alerta, erro, ticket, problema

**Regra**:
Condição determinística e versionada (ex.: INT-003, HTTP 504) que classifica um sintoma e produz Evidências.
_Avoid_: Heurística, detector

**Diagnóstico**:
Versão imutável da análise de um Incidente: classificação, Hipóteses, Evidências, Recomendações e Confiança.
_Avoid_: Análise, resultado, RCA

**Hipótese**:
Explicação candidata para a causa de um Incidente, sempre sustentada por Evidências.
_Avoid_: Causa-raiz (só depois de confirmada), palpite

**Causa provável**:
A Hipótese principal de um Diagnóstico.
_Avoid_: Causa-raiz

**Evidência**:
Fato verificável que aponta para um Evento, Log bruto ou documento de origem.
_Avoid_: Prova, indício

**Confiança**:
Pontuação heurística de 0 a 1 da Causa provável. Não é uma probabilidade calibrada.
_Avoid_: Probabilidade, acurácia

**Inconclusivo**:
Estado do Diagnóstico quando as Evidências não bastam para indicar a Causa provável.
_Avoid_: Falhou, desconhecido

**Recomendação**:
Ação de investigação ou correção sugerida a um humano; nunca é executada automaticamente.
_Avoid_: Ação, fix, remediação

**Revisão humana**:
Avaliação de um Diagnóstico por um Analyst, que o aceita, corrige ou rejeita.
_Avoid_: Feedback (é o registro dela), aprovação

**Sistema responsável**:
Sistema apontado pelo Diagnóstico como origem provável da falha; pode ser "Indeterminado".
_Avoid_: Culpado, owner

## Conhecimento

**Base de conhecimento**:
Documentos e Incidentes resolvidos de uma Organização, consultados pelo Diagnóstico.
_Avoid_: KB (em texto de produto), wiki

**Base global**:
Conhecimento curado pela plataforma (códigos de erro SAP/Salesforce/GCP, padrões conhecidos), somente leitura e igual para todas as Organizações.

**Fragmento**:
Trecho de um documento da Base de conhecimento, indexado para busca semântica.
_Avoid_: Chunk (em texto de produto)

## Saídas

**Relatório técnico**:
Exportação em português de um Incidente e do seu Diagnóstico atual, para outra equipe.
_Avoid_: Laudo, export

**Trilha de auditoria**:
Registro imutável de quem fez o quê, quando e em qual Organização.
_Avoid_: Log (ambíguo com Log bruto), histórico
