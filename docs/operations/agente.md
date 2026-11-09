# Agente local (SAP on-premises)

O agente coleta do SAP que não é alcançável pela internet: roda numa máquina da rede do cliente e só abre conexões de saída para a API. Decisões em [ADR-0015](../adr/0015-agente-local-so-de-saida.md); rotas em [docs/api/agents.md](../api/agents.md).

## Requisitos

- **Máquina:** Linux com Docker (ou Python 3.12), 1 vCPU, 512 MB de RAM e 1 GB de disco para a fila (cerca de 1 milhão de Eventos).
- **Rede:** saída HTTPS (443) para o endereço da API, direto ou pelo proxy da empresa (`HTTPS_PROXY`). **Nenhuma porta de entrada.** Para RFC, acesso da máquina ao servidor de aplicação SAP (porta 33NN, onde NN é o número da instância).
- **Relógio** sincronizado (NTP): requisições com mais de 5 min de diferença são recusadas.

## Instalação

1. Em **Conectores → Agente local → Adicionar**, escolha a Integração e o que o agente pode coletar. O token de registro aparece uma vez e vale 24 h.
2. Na máquina do agente, rode o comando mostrado:

   ```sh
   docker run --rm -v aid-agent:/var/lib/aid-agent ghcr.io/jayv-coder/aid-agent:latest \
     register --api https://api.exemplo.com.br --token aid_reg_…
   docker run -d --name aid-agent --restart unless-stopped -v aid-agent:/var/lib/aid-agent \
     ghcr.io/jayv-coder/aid-agent:latest run
   ```

   O registro gera a chave Ed25519 no volume (`/var/lib/aid-agent/agent.key`, 0600), troca o token pelo segredo do agente e grava os dois no volume. O volume é a identidade do agente: guarde-o como guardaria uma chave.
3. Em até 5 min o card do agente fica **Conectado**, com a versão.

## Coletas

- **Pasta de exportações:** arquivos CSV, NDJSON ou JSON que um job do SAP grava numa pasta montada no contêiner (`-v /exports/sap:/exports/sap:ro`). Os formatos de SM58, SLG1 e status de IDoc são os da Importação manual ([docs/guia](../guia/)). Arquivo novo ou regravado é lido de novo; o `event_id` estável evita duplicar.
- **Status de IDoc via RFC:** `RFC_READ_TABLE` em `EDIDS` (ou `EDIDC`), só os campos de controle e status, a partir da última data lida.
- **Função customizada `Z_AID_…`:** para SLG1 e SM58 sem exportação. Contrato: importa `IV_SINCE` (AAAAMMDDhhmmss) e devolve a tabela `ET_MESSAGES` com `TIMESTAMP`, `TYPE`, `ID`, `NUMBER`, `MESSAGE`, `OBJECT` e `EXTERNAL_ID`.

### Usuário técnico SAP (mínimo privilégio)

Usuário do tipo **Sistema** (sem login de diálogo), com:

- `S_RFC` com `RFC_TYPE = FUGR` e `RFC_NAME` só nos grupos de função usados (`SDTX` para `RFC_READ_TABLE` e o grupo da `Z_AID_…`), `ACTVT = 16`;
- `S_TABU_NAM` com `ACTVT = 03` e `TABLE = EDIDC, EDIDS` (leitura só dessas tabelas);
- nada de `S_TABU_DIS` amplo, `S_DEVELOP` ou perfis `SAP_ALL`/`SAP_NEW`.

As credenciais ficam só na máquina do agente, em variáveis de ambiente: `AID_SAP_ASHOST`, `AID_SAP_SYSNR`, `AID_SAP_CLIENT`, `AID_SAP_USER` e `AID_SAP_PASSWORD`.

### Biblioteca RFC

A imagem não traz biblioteca RFC: o NW RFC SDK tem licença da SAP, e o PyRFC foi descontinuado pela SAP. Para coletar por RFC, derive a imagem com o SDK que a sua empresa já licencia e uma biblioteca compatível com `pyrfc.Connection(...).call(função, **parâmetros)`. Sem ela, as coletas RFC registram erro no log e a coleta por pasta continua.

## Operação

- **Sem rede:** a coleta continua para a fila em disco (`buffer.sqlite3`). Quando a rede volta, o agente envia em lotes de 500, sem duplicar.
- **Revogar:** no card, **Revogar → Confirmar**. A próxima requisição do agente é recusada e ele para com o código 3.
- **Trocar a identidade** (máquina nova, suspeita de vazamento): **Novo token** no card, e `register` de novo com um volume novo.
- **Atualização:** troque a imagem (`docker pull` e recrie o contêiner). Fora do Docker, como zipapp com `AID_AGENT_BINARY`, o agente baixa e aplica só a versão com assinatura válida da chave de release (`AID_AGENT_RELEASE_KEY`) e sai com o código 75 para o supervisor reiniciar.
- **Logs:** só contagens e erros de coleta; nenhum conteúdo de Evento.
