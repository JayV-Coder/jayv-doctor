# Jira Service Management (worker `notifier`)

Rotas em [docs/api/itsm.md](../api/itsm.md); a tela é **Mais → Chamados (ITSM)** (Tela 21) e o card **Chamado** no Incidente.

## Conexão (OAuth 2.0 3LO)

1. Owner ou Admin com MFA clica em **Conectar Jira**; a API grava o hash do `state` (uso único, 10 min) e devolve a URL do consentimento no Atlassian (escopos `read:jira-work write:jira-work manage:jira-webhook read:jira-user offline_access`).
2. O Atlassian volta para o app (`/chamados/jira`), que repassa `code` e `state` à API com a sessão de quem pediu. A API troca pelos tokens e os grava no Vault (`doctor/itsm/<tenant>`) pela função do banco; não os lê de volta.
3. A pessoa escolhe o site, o projeto e o tipo de issue. A conexão fica ativa e o `notifier` registra o webhook dinâmico do Jira (`labels = integration-ai-doctor`, `jira:issue_updated` e `comment_created`), que vence em 30 dias e é renovado pela varredura.

O refresh token do Atlassian gira a cada renovação; o `notifier` grava o novo no Vault na hora. Renovação recusada deixa a conexão `needs_reauth`, e a tela pede para conectar de novo.

## Chamado

- **Abrir:** à mão no Incidente (Analyst ou acima) ou por Regra de alerta com canal `jira`. Os dois passam por `doctor.queue_ticket`, que reserva `incident_tickets` (único por Incidente e provedor) e põe `itsm.ticket` na outbox só na primeira vez. Chamado que falhou pode ser pedido de novo.
- **Conteúdo:** título `[Doctor] <título do Incidente>`, rótulo `integration-ai-doctor`, prioridade pela severidade, campos fixos e, em ADF: Integração, Ambiente, severidade, a Classificação e a Causa provável do último Diagnóstico com **Confiança heurística**, as Recomendações e o link para o Incidente. Nunca Eventos brutos.
- **Status de volta:** o webhook do Jira chega num endereço com token (só o hash fica no banco) e só pede a sincronização; o `notifier` lê o status pela API do Jira com os tokens da Organização. O conteúdo do webhook não é confiado. A varredura sincroniza também os chamados sem leitura há 15 min. Status na categoria `done` vira `done`: a tela sugere resolver o Incidente, e uma pessoa confirma com a nota de resolução.
- **Comentários:** comentário no Jira que começa com `#doctor` vira comentário no Incidente (uma vez, com o nome de quem escreveu); comentário no Doctor que começa com `#jira` vai para o chamado.
