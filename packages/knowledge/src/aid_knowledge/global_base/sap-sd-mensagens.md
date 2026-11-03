# Mensagens de recusa do SAP SD em integrações

Texto original da equipe do Integration AI Doctor. Resume o que costuma estar por trás das mensagens mais frequentes quando um pedido chega ao SAP por BAPI ou IDoc.

## Como ler o BAPIRET2

A tabela RETURN de uma BAPI traz uma linha por mensagem. O campo TYPE diz a gravidade: S (sucesso), I (informação), W (aviso), E (erro) e A (aborto). Uma chamada pode responder HTTP 200 e ainda assim recusar o pedido: o que decide é haver alguma linha E ou A. ID é a classe de mensagem (por exemplo V1 ou VL) e NUMBER é o número dentro da classe. MESSAGE traz o texto já montado, que pode conter números de documento e de cliente.

Depois de uma recusa, nada foi gravado: a BAPI desfaz o que fez, e o BAPI_TRANSACTION_COMMIT não deve ser chamado. Reenviar sem corrigir a causa gera a mesma recusa.

## Classe V1 (documentos de vendas)

Mensagens V1 aparecem na criação e alteração de ordens de venda (BAPI_SALESORDER_CREATEFROMDAT2, VA01). As causas mais comuns são dados mestres incompletos: cliente sem área de vendas, material não liberado para o canal de distribuição, condição de preço ausente, unidade de medida sem conversão ou bloqueio de crédito. Também aparecem quando o documento está sendo editado por outro usuário (bloqueio de objeto).

O que verificar: o cliente e o material na área de vendas usada pela integração, o mapeamento de organização de vendas, canal e setor de atividade, e se a mensagem cita um bloqueio por outro usuário (nesse caso a nova tentativa pode funcionar alguns minutos depois).

## Classe VL (entregas)

Mensagens VL aparecem na criação de remessas a partir de ordens (VL01N, BAPI de entrega). Costumam indicar que não há quantidade confirmada, que a data de remessa não chegou, que o item já foi totalmente fornecido ou que falta determinação de local de expedição. São recusas de regra de negócio: a integração está correta, o estado do documento de origem é que não permite a entrega.

## Bloqueio de objeto e timeout

Quando duas integrações mexem no mesmo documento, o SAP responde com mensagem de bloqueio (o objeto está sendo processado por outro usuário). Se a integração usa um gateway com tempo limite curto, o bloqueio pode aparecer como timeout HTTP 504 do lado de quem chama, sem que o SAP tenha recusado. Nesse caso o resultado no SAP é indeterminado: confirme se o pedido existe antes de reenviar, para não duplicar.
