# O que falta configurar no ambiente real

Tudo foi validado na stack local e no CI. A configuração do GCP e do Supabase hospedado (`exvsozyemolrjbjetqww`, compartilhado com o jayv-coder) fica para uma sessão no fim, com o responsável. Esta lista cresce a cada ticket.

## GCP

- [ ] Autenticar o `gcloud` e rodar `terraform plan` por ambiente. Itens a conferir estão no checklist da PR #60:
  - revisão com `ignore_changes`;
  - plano sem diff depois do primeiro apply;
  - permissões do deployer;
  - DLQ;
  - certificado e rate limit.
- [ ] `environments/*.tfvars`: trocar `project_id`, `app_url`, `api_domain` e `supabase_publishable_key` (`sb_publishable_…`, a mesma do app web) pelos valores reais.
- [ ] Segredos no Secret Manager:
  - `supabase-db-url`;
  - `hmac-master-key`: 32+ bytes aleatórios, que nunca mudam depois do primeiro Evento, porque mudar quebra a busca por Referência;
  - `smtp-url`;
  - `supabase-service-role-key`, usada pelo worker de ingestão para ler o Log bruto no Storage (ticket #12).
- [ ] `MAIL_FROM` com um remetente de domínio verificado.
- [ ] Variáveis do GitHub (`GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA`, `GCP_PROJECT_ID`) e `DEPLOY_ENABLED`.

## Supabase hospedado (exige aprovação na hora, ADR-0009)

- [ ] `scripts/apply-doctor-migrations.py --check` e, na janela combinada, `--apply`. As migrações criam o schema `doctor`, o bucket `doctor-raw-logs` e as políticas dele em `storage.objects`.
- [ ] Confirmar que nenhum Custom Access Token Hook está ativo e ativar `doctor.custom_access_token_hook`.
- [ ] Incluir as URLs do app web nas URLs de redirecionamento do Auth.
- [ ] Confirmar que o schema `doctor` **não** está em "Exposed schemas" da API de dados (PostgREST). `anon` executa as funções do token de ingestão (ticket #12), e expor o schema deixaria chamá-las sem passar pela validação da API. O worker valida de novo, mas a porta certa é só a API.

## App web

- [ ] Definir onde o Next.js roda em produção (ainda sem ticket próprio de deploy) e as variáveis `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_SITE_URL` e `API_URL`.
