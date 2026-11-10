# Chamados de ITSM (worker `notifier`)

Rotas em [docs/api/itsm.md](../api/itsm.md); a tela é **Mais → Chamados (ITSM)** (Tela 21) e o card **Chamado** no Incidente.

## Conexão (OAuth 2.0 3LO)

1. Owner ou Admin com MFA clica em **Conectar Jira**; a API grava o hash do `state` (uso único, 10 min) e devolve a URL do consentimento no Atlassian (escopos `read:jira-work write:jira-work manage:jira-webhook read:jira-user offline_access`).
2. O Atlassian volta para o app (`/chamados/jira`), que repassa `code` e `state` à API com a sessão de quem pediu. A API troca pelos tokens e os grava no Vault (`doctor/itsm/<tenant>`) pela função do banco; não os lê de volta.
3. A pessoa escolhe o site, o projeto e o tipo de issue. A conexão fica ativa e o `notifier` registra o webhook dinâmico do Jira (`labels = integration-ai-doctor`, `jira:issue_updated` e `comment_created`), que vence em 30 dias e é renovado pela varredura.

O refresh token do Atlassian gira a cada renovação; o `notifier` renova sob uma trava por conexão (`pg_advisory_xact_lock`), relê o Vault dentro dela e grava o novo na hora, para que dois workers não gastem o mesmo refresh token. Uma nova configuração tira o webhook anterior do Jira antes de registrar o novo; erro no registro fica em `last_error` e a varredura de 15 min segue lendo os chamados. Renovação recusada deixa a conexão `needs_reauth`, e a tela pede para conectar de novo.

## Chamado

- **Abrir:** à mão no Incidente (Analyst ou acima, conferido na tabela de Vínculos) ou por Regra de alerta com canal `jira` (Mais → Alertas → canal "Jira"). Os dois passam por `doctor.queue_ticket`, que reserva `incident_tickets` (único por Incidente e provedor) e põe `itsm.ticket` na outbox só na primeira vez. Chamado que falhou pode ser pedido de novo.
- **Sem duplicar:** cada tentativa reserva o chamado por 5 min (`claimed_at`) e, antes do POST, procura no Jira a issue com o rótulo `aid-<id do chamado>`; achou, adota. Entrega repetida do Pub/Sub ou worker que caiu depois de criar não abre outra issue. Falha inesperada vira `failed` (com o motivo); chamado preso em `creating` há mais de 5 min é retomado pela varredura.
- **Conteúdo:** título `[Doctor] <título do Incidente>`, rótulo `integration-ai-doctor`, prioridade pela severidade, campos fixos e, em ADF: Integração, Ambiente, severidade, a Classificação e a Causa provável do último Diagnóstico com **Confiança heurística**, as Recomendações e o link para o Incidente. Nunca Eventos brutos.
- **Status de volta:** o webhook do Jira chega num endereço com token (o hash fica na tabela para conferir; o token, no Vault com os tokens do Atlassian, nunca na outbox) e só pede a sincronização, com limite de taxa por endereço. Eventos repetidos da mesma issue viram uma leitura só enquanto a anterior não saiu, e o evento com a chave da issue relê só aquele chamado; o `notifier` lê o status pela API do Jira com os tokens da Organização. O conteúdo do webhook não é confiado. A varredura sincroniza também os chamados sem leitura há 15 min. Status na categoria `done` vira `done`: a tela sugere resolver o Incidente, e uma pessoa confirma com a nota de resolução.
- **Comentários:** comentário no Jira que começa com `#doctor` vira comentário no Incidente (uma vez, com o nome de quem escreveu); comentário no Doctor que começa com `#jira` vai para o chamado.

## ServiceNow (#44)

### Conexão

1. Na instância do cliente, um administrador cria em **System OAuth → Application Registry** um *OAuth API endpoint for external clients* com o grant **Client Credentials** (Washington DC ou mais nova; propriedade `glide.oauth.inbound.client.credential.grant_type.enabled = true`) e um usuário de integração com os papéis `itil` (criar e ler `incident`) e acesso aos grupos de atendimento.
2. Owner ou Admin com MFA informa em **Mais → Chamados (ITSM)** a instância (`https://<instância>.service-now.com`; outro domínio é recusado), o client id e o client secret, a regra de grupos por Sistema responsável e o grupo padrão. O secret vai para o Vault (`doctor/itsm-servicenow/<tenant>`) e não volta em nenhuma resposta; trocar a instância ou o client id exige o secret de novo.
3. O `notifier` confere as credenciais pedindo um token (`oauth_token.do`). Recusou: a conexão fica `needs_reauth` com o motivo, e a tela pede para conferir. O token de acesso fica só na memória da rodada.

### Incident

- **Abrir:** à mão no Incidente ("Abrir chamado no ServiceNow") ou por Regra de alerta com canal `servicenow`, pela mesma reserva única de `incident_tickets` do Jira (um por Incidente e provedor).
- **Grupo:** o Sistema responsável do último Diagnóstico (SAP, Salesforce, GCP, Outro) escolhe o grupo pela regra da Organização; sem Sistema ("Indeterminado") ou sem grupo para ele, vai o grupo padrão. Nome ou sys_id: a criação usa `sysparm_input_display_value=true`.
- **Conteúdo:** `short_description` `[Doctor] <título>`, `impact` e `urgency` pela severidade, `correlation_id` com o id do chamado e, nas `work_notes`, a Classificação, a Causa provável com **Confiança heurística**, o Sistema responsável, as Recomendações e o link. Nunca Eventos brutos.
- **Sem duplicar:** a tentativa reserva o chamado por 5 min e, antes do POST, procura o incident pelo `correlation_id`; achou, adota.

### Status de volta (Business Rule)

A configuração mostra uma vez o endereço do webhook (`/api/v1/itsm/servicenow/hooks/<token>`; o banco guarda só o hash). No ServiceNow, crie uma Business Rule **after update** na tabela `incident`, com a condição `State changes` e `Correlation display is Integration AI Doctor`:

```javascript
(function executeRule(current, previous) {
  var request = new sn_ws.RESTMessageV2();
  request.setEndpoint(gs.getProperty('x_aid.doctor_hook_url')); // o endereço mostrado na configuração
  request.setHttpMethod('POST');
  request.setRequestHeader('Content-Type', 'application/json');
  request.setRequestBody(JSON.stringify({ number: current.getValue('number') }));
  request.executeAsync();
})(current, previous);
```

O corpo só diz qual incident reler: o `notifier` lê o `state` pela Table API com as credenciais da Organização. Resolvido (6), Fechado (7) ou Cancelado (8) viram `done` e a tela sugere resolver o Incidente; uma pessoa confirma com a nota. Sem a Business Rule, a varredura lê os chamados abertos a cada 15 min. "Gerar outro endereço" invalida o anterior.
