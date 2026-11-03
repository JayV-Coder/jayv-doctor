# Limites e erros comuns do Salesforce em integrações

Texto original da equipe do Integration AI Doctor.

## Limite diário de chamadas de API

Cada organização do Salesforce tem uma cota de chamadas de API em 24 horas, que depende da edição e do número de licenças. Ao estourar, as chamadas passam a responder REQUEST_LIMIT_EXCEEDED até a janela andar. Integrações que fazem polling frequente ou consultas uma a uma são as que mais consomem: prefira consultas em lote e eventos.

## Limites de governança (Apex)

Gatilhos e classes Apex que rodam na gravação de um registro têm limites por transação: número de consultas SOQL, linhas retornadas, operações DML e tempo de CPU. Uma integração que grava muitos registros de uma vez pode estourar esses limites por causa de gatilhos do cliente, e o erro aparece como falha da gravação. Grave em lotes menores ou revise o gatilho.

## Sessão expirada e credenciais

INVALID_SESSION_ID indica token expirado ou revogado. Em integrações com OAuth, o refresh token pode ter sido revogado por política de sessão ou pela troca de senha do usuário de integração. Verifique o usuário de integração, a política de sessão do aplicativo conectado e se o IP de origem está liberado.

## Bloqueio de registro

UNABLE_TO_LOCK_ROW indica que outra transação está alterando o mesmo registro (ou um registro pai) ao mesmo tempo. Acontece com cargas paralelas sobre a mesma conta. Repetir depois de alguns segundos costuma resolver; reduzir o paralelismo por registro pai evita.

## Outbound Messages

Mensagens de saída são reenviadas pelo Salesforce até receberem confirmação (ACK) do endpoint, por até 24 horas. Um endpoint que responde fora do tempo ou sem o ACK correto recebe a mesma mensagem várias vezes: a integração precisa ser idempotente.
