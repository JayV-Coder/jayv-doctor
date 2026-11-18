# Railway

Alternativa ao GCP para rodar a plataforma inteira, no lugar do antigo Dokploy ([ADR-0024](../adr/0024-railway-com-rabbitmq.md)). O projeto é descrito em [.railway/railway.ts](../../.railway/railway.ts) (Infrastructure as Code do Railway). Ele tem 9 serviços e um volume:

| Serviço | O que é | Rede |
|---|---|---|
| `api` | API (`aid_api.main:app`) | domínio público, porta 8080 |
| `worker-ingestion`, `worker-correlation`, `worker-diagnosis`, `worker-connectors`, `worker-notifier` | workers: consomem as filas dos seus tópicos e atendem as rotas do agendador | privada (`<serviço>.railway.internal:8080`) |
| `worker-relay` | relay da outbox: publica no RabbitMQ ([outbox.md](outbox.md)) | privada |
| `scheduler` | os jobs do Cloud Scheduler, a cada minuto (`python -m aid_worker.scheduler`) | só sai |
| `rabbitmq` | o broker no lugar do Pub/Sub, com o volume `rabbitmq-data` em `/var/lib/rabbitmq` | privada, porta 5672 |

Todos os serviços Python saem do mesmo `infrastructure/docker/python.Dockerfile`; as variáveis `PACKAGE`, `APP` e `SYSTEM_PACKAGES` de cada serviço viram argumentos do build. Eles escutam em `HOST=::`, porque a rede privada do Railway pode ser só IPv6. Ficam de fora o envio de métricas ao Cloud Monitoring, o backup do Storage no GCS, o tracing (OTEL desligado) e os perfis de IA do Brasil e dedicado (Vertex AI).

## Filas no RabbitMQ

O relay publica cada mensagem da outbox na exchange `aid`, com a routing key do tópico, e espera a confirmação do broker. Cada tópico tem a sua fila (`aid.<tópico>`, quorum), e o worker do tópico a consome. O comportamento é o das assinaturas do Pub/Sub no Terraform:

- sucesso confirma a mensagem;
- falha volta à fila depois de 10 s, 30 s, 90 s e 270 s (filas `aid.retry.<n>s`);
- depois da 5ª falha, a mensagem vai para `aid.dead.<tópico>` e fica 7 dias;
- se o worker cair no meio, o broker reentrega; a fila quorum manda à DLQ a mensagem que derruba o worker 5 vezes.

Mensagem de tópico sem fila volta para o relay e conta uma tentativa na outbox, como a recusa do Pub/Sub. Quem conecta (relay e workers) declara as filas; a declaração é idempotente.

Para ver as DLQs: `railway ssh --service rabbitmq` e depois `rabbitmqctl list_queues name messages | grep dead`.

## Antes do primeiro deploy (projeto Supabase compartilhado)

O Railway usa o projeto `exvsozyemolrjbjetqww`, junto com o jayv-coder ([environments.md](environments.md)). Na janela combinada:

1. Aplicar as migrações do Doctor com `scripts/apply-doctor-migrations.py --check` e depois `--apply` (URL direta, porta 5432). Elas vêm do submódulo `vendor/supabase` (ADR-0022): rode `git submodule update --init` antes.
2. Ligar o Custom Access Token Hook (`doctor.custom_access_token_hook`), conferindo antes que não há outro hook. Em seguida, testar o login do jayv-coder.
3. O app é o site da JayV (`/doctor`, ADR-0023): no serviço do site, defina `DOCTOR_API_URL` com o domínio da `api`.
4. Rodar a Base global uma vez, desta pasta e com as variáveis do serviço: `railway run --service worker-diagnosis uv run python -m aid_knowledge.global_seed`.

## Criar o projeto

1. Instale o Railway CLI (5.42.1 ou mais novo), entre (`railway login`) e crie o projeto vazio no painel, ligado ao GitHub `JayV-Coder/jayv-doctor`. Na pasta do repositório, `railway link` escolhe o projeto e o ambiente `production`.
2. Em **Project Settings → Shared Variables**, crie as variáveis da tabela abaixo, para o ambiente `production`.
3. `pnpm install` (instala o SDK do `.railway/`), `railway config plan` para conferir e `railway config apply` para criar os serviços e o volume.
4. Na `api`, em **Settings → Networking**, gere o domínio público na porta 8080 (ou ligue um domínio próprio). Os workers, o agendador e o RabbitMQ ficam sem domínio.
5. Faça o deploy. O log de cada worker mostra `consumindo N filas do RabbitMQ`; o do `scheduler` mostra os jobs a cada minuto.

Mudanças no `.railway/railway.ts` só valem depois de `railway config apply`: o Railway não lê o arquivo no deploy. Recurso que sai do arquivo é apagado no próximo apply.

## Variáveis compartilhadas

| Variável | Valor | Quem usa |
|---|---|---|
| `SUPABASE_URL` | `https://exvsozyemolrjbjetqww.supabase.co` | todos (e vira `SUPABASE_JWT_ISSUER`) |
| `SUPABASE_PUBLISHABLE_KEY` | `sb_publishable_7PeIEX0yh_svIEeNw3Gwew_lEbMVtMm` (pública) | API |
| `SUPABASE_DB_URL` | pooler de transações, porta 6543: `postgresql://postgres.exvsozyemolrjbjetqww:<senha>@aws-0-sa-east-1.pooler.supabase.com:6543/postgres` (Dashboard → Connect) | API e workers |
| `SUPABASE_SERVICE_ROLE_KEY` | Dashboard → Settings → API Keys → secret key | workers de ingestão e diagnóstico |
| `APP_URL` | origem do site (`https://jayv…`), sem barra no fim: os links levam a `/doctor/…` (ADR-0023) | API e notifier |
| `SMTP_URL` | `smtp://usuario:senha@host:587` do provedor de e-mail | API e workers |
| `MAIL_FROM` | remetente (opcional) | API e workers |
| `HMAC_MASTER_KEY` | gerar: `openssl rand -hex 32`. **Guarde:** trocar invalida as Referências de negócio já gravadas | API e ingestão |
| `RABBITMQ_PASSWORD` | gerar: `openssl rand -hex 24` | RabbitMQ (e a `AMQP_URL` dos workers) |
| `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY` | chaves da Anthropic e da Voyage (sem elas, Diagnóstico só com Regras e Base só pelo texto) | diagnóstico (Voyage também na API) |
| `LLM_ROUTING` | `{}` (sempre o modelo maior; ADR-0020) | diagnóstico |
| `LLM_PRICES` | opcional, preços por modelo (JSON) para o custo no Uso | diagnóstico |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | gerar com o comando de [alertas.md](alertas.md) (a privada em PEM numa linha só, com `\n`, ou DER em base64) | API (pública) e notifier (privada) |
| `VAPID_SUBJECT` | `mailto:` de contato | notifier |
| `ATLASSIAN_CLIENT_ID`, `ATLASSIAN_CLIENT_SECRET` | app OAuth do Jira (opcional, [itsm.md](itsm.md)); callback `<APP_URL>/doctor/tickets/jira` | API e notifier |
| `AGENT_CA_KEY`, `AGENT_CA_CERT` | CA do mTLS do agente (opcional, [agente.md](agente.md)) | API |
| `SUPABASE_ACCESS_TOKEN`, `SUPABASE_PROJECT_REF` | SSO (opcional, [sso.md](sso.md)) | notifier |

Marque as chaves e senhas como *sealed*: o valor some do painel e do `railway config pull`. O endereço público da API (`AID_PUBLIC_API_URL`) e a `AMQP_URL` vêm de referências a outros serviços, sem variável compartilhada.

## Região

O Railway não tem região na América do Sul, e o banco fica em `sa-east-1`. Cada consulta cruza o continente: prefira a região US East (Virgínia), a mais próxima de São Paulo, para todos os serviços e o volume.
