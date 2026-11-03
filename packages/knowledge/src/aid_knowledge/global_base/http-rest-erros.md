# Códigos HTTP em integrações REST

Texto original da equipe do Integration AI Doctor.

## 400 e 422: payload recusado

400 indica requisição malformada (JSON inválido, campo obrigatório ausente, tipo errado). 422 indica um payload bem formado que viola uma regra de validação. Não adianta repetir: o mesmo corpo terá a mesma resposta. Compare o payload com o contrato do destino e procure mudanças recentes de versão da API.

## 401 e 403: autenticação e autorização

401 significa credencial ausente, expirada ou inválida: token OAuth vencido, segredo rotacionado do lado do destino, relógio fora de sincronia. 403 significa que a credencial é válida mas não tem permissão para a operação ou para o recurso. Erros que começam todos ao mesmo tempo depois de uma rotação de segredo apontam para credencial.

## 409: conflito e duplicidade

409 costuma indicar que o identificador já existe ou que houve edição concorrente. Em integrações com retry, um 409 depois de um timeout muitas vezes significa que a primeira tentativa foi gravada: trate como sucesso provável e confirme pelo identificador.

## 429: limite de chamadas

429 indica limite de taxa. O cabeçalho Retry-After diz quanto esperar. Rajadas de reprocessamento e jobs paralelos são a causa típica. Reduza a concorrência e use backoff exponencial com jitter.

## 500, 502, 503 e 504

500 é erro interno do destino. 502 e 503 indicam serviço indisponível ou sobrecarregado no caminho. 504 é tempo esgotado num gateway ou proxy: o destino pode ter concluído a operação depois que o gateway desistiu. Depois de um 504, o resultado remoto é indeterminado: verifique antes de reenviar uma operação que não é idempotente.
