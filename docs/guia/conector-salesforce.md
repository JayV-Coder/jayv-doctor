# Conector Salesforce

O Conector lê os registros de integração da sua org Salesforce e os transforma em Eventos. Ele **só lê** e não usa senha de usuário: o acesso é por uma Connected App.

## Antes: a Connected App

Peça ao administrador do Salesforce:

1. Uma **Connected App** com OAuth, os escopos `api` e `refresh_token`, e **Use digital signatures** com um certificado. Guarde a chave privada dele.
2. Um **usuário de integração** com leitura nos objetos de log, pré-autorizado na Connected App (Manage → Edit Policies → *Admin approved users are pre-authorized*).

## No Doctor

**Conectores → Adicionar → Salesforce** (Owner ou Admin). O assistente tem quatro passos:

1. **Org:** o nome, produção ou sandbox, e o objeto de log de integração (`Integration_Log__c`, por exemplo), se a sua org tiver um.
2. **Credencial:** **JWT Bearer** (recomendado) com o **Consumer Key**, o **Usuário de integração** e a **Chave privada do certificado (PEM)**, ou o Web Server Flow com refresh token. **Testar conexão** confere o acesso e mostra quais fontes a sua edição tem. Sem Event Monitoring, por exemplo, aparece "EventLogFile indisponível nesta edição", e o Conector segue com as outras.
3. **Fontes:** as disponíveis já vêm marcadas. Para o objeto de log, informe o **Campo da mensagem** e o **Campo da severidade**. Escolha também o **Intervalo**.
4. **Ativar:** escolha a **Integração vinculada** e **Ativar conector**.

A credencial vai para o cofre (Vault) e não volta para a tela. O Doctor só consulta os objetos e campos escolhidos, sempre com limite de registros. Não existe consulta livre.

## Limite de API

O Salesforce conta as chamadas de API por dia. Quando o uso da org chega a **80% do limite diário**, a coleta espera sozinha ("Aguardando: o limite diário da API do provedor chegou a 80%"), deixando o restante para os sistemas do cliente, e volta na janela seguinte, sem precisar de ninguém. Trocar a credencial não antecipa a volta.
