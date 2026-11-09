# Agente local: só de saída, chave gerada na máquina e status conferido a cada chamada

O SAP on-premises de muitos clientes não é alcançável pela internet, e abrir uma porta de entrada para a plataforma é o tipo de pedido que a segurança do cliente recusa. O agente (#39) inverte a direção: roda na rede do cliente e só abre conexões HTTPS de saída para a API. Não escuta em porta nenhuma, nem para receber comandos; a configuração chega por long-poll (`GET /api/v1/agent/config`, até 25 s, abaixo dos 30 s comuns de proxy corporativo).

**Identidade.** O ticket pede um certificado mTLS por agente. O Cloud Run não termina mTLS, e pôr um balanceador com mTLS na frente só da rota do agente é infraestrutura que ainda não temos. Então a prova de identidade fica na aplicação, e o certificado vem junto para quando o balanceador existir:

1. Owner ou Admin com MFA cria o agente na tela e recebe um token de registro de uso único (24 h, só o hash no banco).
2. Na máquina do cliente, o agente gera um par Ed25519. A chave privada nunca sai de lá (arquivo 0600).
3. `POST /api/v1/agent/register` com o token e a chave pública. A API devolve o segredo do agente (`aid_agt_…`, só o hash no banco) e, se a CA da plataforma estiver configurada (`AID_AGENT_CA_KEY` e `AID_AGENT_CA_CERT`), um certificado X.509 de cliente para essa chave, com 90 dias. O fingerprint da chave fica na tela.
4. Toda requisição leva o segredo e a assinatura Ed25519 de `método`, `caminho`, instante e sha256 do corpo. A API confere a assinatura com a chave registrada e recusa instante fora de ±5 min.

Roubar só o segredo (num log de proxy, por exemplo) não basta: falta a chave privada. Uma requisição capturada pode ser repetida dentro da janela de 5 min, mas o TLS protege o transporte, e o único efeito de repetir um lote é a deduplicação descartá-lo pelo `event_id`.

**Revogação.** As funções do agente (`resolve_agent`, `accept_agent_batch`, `agent_seen`) conferem o status no banco a cada chamada, sem cache. Revogar recusa a próxima requisição, o que atende ao "< 1 min" do ticket sem lista de revogação de certificados. Rotação é revogar a identidade atual e emitir um token novo para o mesmo agente, que se registra de novo com chave nova.

**Coletas.** O agente só faz o que a config da plataforma autoriza, e a API valida a config contra uma allowlist: pasta de exportações (caminho absoluto, sem `..`), `RFC_READ_TABLE` só em `EDIDC` e `EDIDS` com campos fixos, e funções customizadas só com o prefixo `Z_AID_`. Não há consulta livre nem comando remoto. A Sanitização roda no agente, antes da fila em disco, e de novo na plataforma, que tem a chave das Referências de negócio.

**Atualização.** A plataforma anuncia versão, URL, sha256 e a assinatura Ed25519 da chave de release. O agente só troca o binário com assinatura válida (chave pública fixada na imagem, `AID_AGENT_RELEASE_KEY`), URL `https://` e sha256 batendo. Na imagem Docker, a atualização é trocar a imagem; o anúncio só aparece no log.

## Consequências

- Nenhuma porta de entrada no cliente; o CI confere que a imagem não expõe porta e um teste confere que o código do agente não abre servidor.
- O segredo e a chave privada ficam no volume do agente. Quem tem root na máquina do agente se passa por ele até a revogação, como em qualquer agente.
- O lote do agente entra pelo mesmo caminho da ingestão por API (`ingestion_batches`, outbox `ingestion.raw`), com a mesma Cota e os mesmos limites.
- `anon` ganha quatro funções (registro, resolução, sinal de vida e lote), todas exigindo o hash de um segredo de 256 bits. O inventário dos testes `10_ingestion_tokens` e `30_conventions` as lista.
- O PyRFC foi descontinuado pela SAP e o NW RFC SDK tem licença da SAP; a imagem não traz biblioteca RFC. A coleta RFC funciona com a biblioteca que o cliente instalar numa imagem derivada. A coleta por pasta não depende disso.
