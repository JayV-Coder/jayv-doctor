# Mensagens SAP de MM, FI e IDoc em integrações

Texto original da equipe do Integration AI Doctor. Resume o que costuma estar por trás das mensagens SAP mais frequentes fora de vendas, quando uma integração lança documentos de material, contabilidade ou IDocs. Como em toda mensagem SAP, a classe (ID) e o número identificam a mensagem; o texto vem montado com os dados do documento.

## Bloqueio de objeto (MC 601)

A mensagem MC 601 diz que o objeto pedido está bloqueado por outro usuário: outra transação ou outra integração está editando o mesmo material, pedido ou documento naquele instante. O SAP não gravou nada. Na maioria dos casos, uma nova tentativa alguns minutos depois funciona; se o bloqueio persiste, a transação SM12 mostra quem segura o lock e há quanto tempo. Bloqueios recorrentes no mesmo horário costumam vir de jobs em lote que disputam os mesmos objetos com a integração.

## Material não mantido no centro (M3 305)

A mensagem M3 305 aparece quando o material existe, mas não tem a visão de dados do centro usada pelo documento. É cadastro mestre incompleto, não erro da integração: reenviar não resolve até alguém ampliar o material para o centro (transação MM01/MM50) ou corrigir o centro que a integração envia. Vale conferir também o mapeamento de centro entre o sistema de origem e o SAP.

## Saldo insuficiente em estoque (M7 021)

M7 021 indica falta de estoque de utilização livre para a movimentação pedida (saída de mercadoria, transferência). O lançamento é recusado inteiro. As causas comuns são uma entrada que ainda não foi lançada, estoque em outro depósito ou lote, ou uma movimentação concorrente que consumiu o saldo. Confira o saldo atual (MMBE) antes de reenviar.

## Lançamento contábil desbalanceado (F5 702)

F5 702 aparece quando débitos e créditos do documento contábil não fecham na moeda da transação. Em integrações, costuma vir de arredondamento na conversão de moeda, de um item de imposto que não foi enviado ou de linhas de valor zero descartadas no meio do caminho. O documento não é gravado; a correção é no cálculo ou no mapeamento dos itens.

## Conta sem objeto de custo (KI 235)

KI 235 diz que a conta contábil exige uma atribuição de controladoria (centro de custo, ordem, elemento PEP) e o lançamento chegou sem ela. É regra de cadastro do plano de contas: a integração precisa enviar o objeto de custo, ou a conta usada não é a certa para aquele tipo de lançamento.

## Status de IDoc

O status do IDoc conta onde ele parou:

- **53:** documento de aplicação lançado, ou seja, tudo certo.
- **51:** documento de aplicação não lançado. O IDoc chegou, mas a aplicação recusou; a mensagem do status traz a causa (muitas vezes uma das acima). Depois de corrigir, o IDoc pode ser reprocessado (BD87) sem reenvio pela origem.
- **64:** pronto para ser processado, mas ainda não foi. Se fica muito tempo assim, o job de processamento de entrada está parado ou atrasado.
- **56:** IDoc com erro de estrutura ou de parceiro, recusado antes de chegar à aplicação. Costuma ser configuração (perfil de parceiro, tipo de mensagem).

Reenviar pela origem um IDoc que está em 51 cria outro IDoc com os mesmos dados: se o primeiro for reprocessado depois, o documento pode ser criado duas vezes.

## Chamadas tRFC pendentes (SM58)

Chamadas tRFC que falham ficam listadas na SM58 com o texto do erro. As mais comuns em integrações são credencial do usuário técnico expirada ou bloqueada, destino RFC sem conexão e falta de autorização para o módulo de função. Enquanto a causa não é resolvida, as chamadas se acumulam; depois, elas podem ser executadas de novo pela própria SM58, na ordem.

## Falta de autorização

Mensagens de autorização (por exemplo, "No authorization for…" ou "Sem autorização para…") significam que o usuário técnico da integração não tem o objeto de autorização exigido pela transação ou BAPI. O log de verificação de autorização (SU53, ou o trace da ST01) mostra exatamente o objeto e o campo que faltaram. A correção é no perfil do usuário técnico, com o mínimo necessário, e não em tentar de novo.
