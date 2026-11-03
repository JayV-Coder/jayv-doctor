# Erros de Cloud Run e Cloud Logging em integrações

Texto original da equipe do Integration AI Doctor.

## Tempo limite de requisição do Cloud Run

Cada serviço do Cloud Run tem um tempo limite de requisição. Quando a chamada a um sistema lento (como o SAP) passa desse tempo, o Cloud Run encerra a requisição e o chamador recebe 504. A operação no destino pode continuar e terminar depois. Aumente o tempo limite ou torne o processamento assíncrono, e trate o 504 como resultado indeterminado.

## Partida a frio e escala

Uma instância nova leva alguns segundos para iniciar. Com mínimo de instâncias em zero, a primeira requisição depois de um período ocioso fica mais lenta e pode estourar tempos limite curtos de quem chama. Picos de tráfego também criam instâncias novas. Se os timeouts aparecem logo depois de períodos sem tráfego, configure instâncias mínimas.

## Memória e reinícios

Uma instância que passa do limite de memória é encerrada, e as requisições em andamento falham com 500 ou 503. Nos logs aparece a mensagem de memória excedida. Processar arquivos grandes inteiros em memória é a causa típica.

## Permissão no Cloud Logging

Para ler logs pela API, a conta de serviço precisa da permissão logging.logEntries.list no projeto, normalmente pelo papel roles/logging.viewer. Sem ela, a leitura responde PERMISSION_DENIED. Se a API do Cloud Logging estiver desativada no projeto, a resposta também é 403, mas com o motivo SERVICE_DISABLED.

## Cota de leitura

A API de leitura de entradas do Cloud Logging tem cota por minuto por projeto. Leituras muito frequentes ou paginação agressiva estouram a cota e recebem RESOURCE_EXHAUSTED (429). Espaçar as leituras resolve.
