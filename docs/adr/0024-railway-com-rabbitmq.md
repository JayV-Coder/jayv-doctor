# Railway com RabbitMQ no lugar do Dokploy

O ambiente fora do GCP passa do Dokploy para o Railway, descrito em `.railway/railway.ts` (Infrastructure as Code do Railway). O Pub/Sub dá lugar a um RabbitMQ com volume na rede privada do projeto. No GCP nada muda: o Terraform segue com Cloud Run, Pub/Sub e Cloud Scheduler.

O código ganha um segundo adaptador de mensageria, escolhido por `AMQP_URL`:

- **Relay** (`aid_relay.rabbit.RabbitPublisher`): publica na exchange `aid` com a routing key do tópico, com `mandatory` e confirmação do broker. Mensagem sem fila conta tentativa na outbox, como a recusa do Pub/Sub.
- **Workers** (`aid_worker.rabbit.Consumer`): cada um consome as filas dos seus tópicos e chama o mesmo handler do push (`process`). A falha volta depois de uma espera crescente; depois da 5ª, vai para a DLQ do tópico, que guarda por 7 dias.

Os handlers, a outbox, os tópicos e os jobs do agendador são os mesmos nos dois ambientes.

## Consequências

- **O Railway diverge do GCP na mensageria.** Um teste do adaptador do Pub/Sub não cobre o do RabbitMQ, e vice-versa. Os dois têm testes de integração no CI, contra o emulador e contra um RabbitMQ real.
- **O broker é nosso.** O RabbitMQ roda num nó só, com volume e sem réplica. Reiniciar o broker não perde mensagem confirmada, porque as filas ficam no volume, e a que estava em processamento é reentregue. Perder o volume perde as mensagens em fila, mas não a outbox, que fica no banco.
- **O agendador chama os workers pela rede privada** (`worker-<nome>.railway.internal:8080`). As rotas dos jobs não têm autenticação: só a `api` tem domínio público.
- **Variáveis compartilhadas** guardam segredos e URLs. O `railway.ts` só as liga aos serviços, então nenhum segredo vai para o repositório.
- **Ficam de fora**, como no Dokploy:
  - métricas no Cloud Monitoring;
  - backup do Storage no GCS;
  - tracing;
  - perfis de IA do Brasil e dedicado (Vertex AI).

## Considered Options

- **Emulador do Pub/Sub, como no Dokploy:** paridade com o GCP e quase nenhum código, mas o emulador guarda tudo em memória. Reiniciar perde as mensagens em trânsito e as assinaturas, que o agendador precisava recriar.
- **Kafka:** não tem confirmação nem reentrega por mensagem, então as novas tentativas e a DLQ viriam de tópicos extras mantidos pelo código. Um Diagnóstico de até 10 minutos seguraria a partição. Um broker de um nó pede pelo menos 1 GB de memória. O volume do Doctor, que sai da outbox, não usa o que o Kafka tem de melhor: replay e vazão alta.
- **Pub/Sub de verdade a partir do Railway:** cada worker precisaria de domínio público e de validar o OIDC do push, além de uma credencial de conta de serviço do GCP fora do GCP.
- **RabbitMQ também no GCP:** um caminho só no código, mas troca um serviço gerenciado por um broker a operar em produção.
