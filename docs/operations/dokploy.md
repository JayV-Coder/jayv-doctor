# Teste no Dokploy

Alternativa ao GCP para testar a plataforma inteira: [infrastructure/dokploy/docker-compose.yml](../../infrastructure/dokploy/docker-compose.yml). O Pub/Sub vira o emulador (`pubsub` + `pubsub-setup`, que cria os 18 tópicos e as assinaturas push) e o Cloud Scheduler vira o serviço `scheduler`. Ficam de fora o envio de métricas ao Cloud Monitoring e o backup do Storage no GCS, e o tracing (OTEL desligado). Testes conferem que tópicos e jobs são os mesmos do Terraform.

## Antes do primeiro deploy (projeto Supabase compartilhado)

O Dokploy usa o projeto `exvsozyemolrjbjetqww`, junto com o jayv-coder ([environments.md](environments.md)). Na janela combinada:

1. Aplicar as migrações do Doctor com `scripts/apply-doctor-migrations.py --check` e depois `--apply` (URL direta, porta 5432).
2. Ligar o Custom Access Token Hook (`doctor.custom_access_token_hook`), conferindo antes que não há outro hook. Em seguida, testar o login do jayv-coder.
3. Acrescentar `https://<APP_URL>/auth/callback**` às URLs de redirecionamento do Auth.
4. Rodar a Base global uma vez: `python -m aid_knowledge.global_seed`, com `SUPABASE_DB_URL` e `VOYAGE_API_KEY`.

## No Dokploy

1. Crie um serviço **Docker Compose** apontando para o repositório e a branch a testar, com o arquivo `infrastructure/dokploy/docker-compose.yml`.
2. Em **Environment**, cole as variáveis de [infrastructure/dokploy/.env.example](../../infrastructure/dokploy/.env.example), preenchidas (tabela abaixo).
3. Em **Domains**, crie dois domínios com HTTPS: `web`, porta 3000 (`APP_URL`), e `api`, porta 8080 (`API_PUBLIC_URL`). Os workers, o emulador e o agendador não recebem domínio.
4. Faça o deploy. O `pubsub-setup` sai com código 0 depois de criar os tópicos. Se o `pubsub` reiniciar, ele perde tudo (o emulador guarda em memória): rode o deploy de novo.

## Variáveis

| Variável | Valor | Onde vai |
|---|---|---|
| `SUPABASE_URL` | `https://exvsozyemolrjbjetqww.supabase.co` | todos (e vira `NEXT_PUBLIC_SUPABASE_URL` e `SUPABASE_JWT_ISSUER`) |
| `SUPABASE_PUBLISHABLE_KEY` | `sb_publishable_7PeIEX0yh_svIEeNw3Gwew_lEbMVtMm` (pública) | web e API |
| `SUPABASE_DB_URL` | pooler de transações, porta 6543: `postgresql://postgres.exvsozyemolrjbjetqww:<senha>@aws-0-sa-east-1.pooler.supabase.com:6543/postgres` (Dashboard → Connect) | API e workers |
| `SUPABASE_SERVICE_ROLE_KEY` | Dashboard → Settings → API Keys → secret key | workers de ingestão e diagnóstico |
| `APP_URL` | domínio da web, sem barra no fim | web, API e notifier |
| `API_PUBLIC_URL` | domínio da API, sem barra no fim | API e notifier (webhooks de ITSM) |
| `SMTP_URL` | `smtp://usuario:senha@host:587` do provedor de e-mail | API e workers |
| `MAIL_FROM` | remetente (opcional) | API e workers |
| `HMAC_MASTER_KEY` | gerar: `openssl rand -hex 32`. **Guarde:** trocar invalida as Referências de negócio já gravadas | API e ingestão |
| `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY` | chaves da Anthropic e da Voyage (sem elas, Diagnóstico só com Regras e Base só pelo texto) | diagnóstico (Voyage também na API) |
| `LLM_ROUTING` | `{}` (sempre o modelo maior; ADR-0020) | diagnóstico |
| `LLM_PRICES` | opcional, preços por modelo (JSON) para o custo no Uso | diagnóstico |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | gerar com o comando de [alertas.md](alertas.md) (a privada em PEM numa linha só, com `\n`, ou DER em base64) | API (pública) e notifier (privada) |
| `VAPID_SUBJECT` | `mailto:` de contato | notifier |
| `ATLASSIAN_CLIENT_ID`, `ATLASSIAN_CLIENT_SECRET` | app OAuth do Jira (opcional, [itsm.md](itsm.md)); callback `<APP_URL>/chamados/jira` | API e notifier |
| `AGENT_CA_KEY`, `AGENT_CA_CERT` | CA do mTLS do agente (opcional, [agente.md](agente.md)) | API |
| `GCP_PROJECT_ID`, `LOG_LEVEL`, `RATE_LIMIT_PER_MINUTE` | `aid-local`, `INFO`, `120` | todos |

Os perfis de IA do Brasil e dedicado (#45) precisam do Vertex AI, que exige credencial do GCP. No Dokploy, use o perfil padrão.
