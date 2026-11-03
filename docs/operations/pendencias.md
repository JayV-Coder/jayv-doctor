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
  - `supabase-service-role-key`, usada pelo worker de ingestão para ler o Log bruto no Storage (ticket #12);
  - `anthropic-api-key` e `voyage-api-key`, do worker de diagnóstico (ticket #22); a `voyage-api-key` também na API, para a busca da Base de conhecimento (ticket #23).
- [ ] Vertex AI (provedor alternativo de IA, ticket #22): ativar a API no projeto, dar `roles/aiplatform.user` à conta do worker de diagnóstico, definir `GCP_PROJECT_ID` nele e confirmar que `gemini-2.5-pro`, `gemini-2.5-flash` e `text-embedding-005` estão disponíveis em southamerica-east1.
- [ ] `MAIL_FROM` com um remetente de domínio verificado.
- [ ] Variáveis do GitHub (`GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA`, `GCP_PROJECT_ID`) e `DEPLOY_ENABLED`.

- [ ] Teste do conector GCP (ticket #15) em staging, contra um projeto de teste com logs sintéticos: comparar a contagem do Logging com os Eventos gravados, com uma Sincronização por minuto.
- [ ] Decidir e montar a identidade de plataforma por Organização, que liga o modo sem chave (`impersonation`) do conector GCP (ver `docs/operations/conectores.md`).

## Supabase hospedado (exige aprovação na hora, ADR-0009)

- [ ] `scripts/apply-doctor-migrations.py --check` e, na janela combinada, `--apply`. As migrações criam o schema `doctor`, o bucket `doctor-raw-logs` e as políticas dele em `storage.objects`.
- [ ] Extensão `vector` (pgvector, ticket #23): a migração da Base de conhecimento a cria no schema `extensions`. Instalar extensão no projeto compartilhado exige aprovação na janela; conferir antes se o jayv-coder já a usa. A busca usa `hnsw.iterative_scan` (pgvector ≥ 0.8): conferir a versão (`select extversion from pg_extension where extname = 'vector'`).
- [ ] Rodar `python -m aid_knowledge.global_seed` (com `SUPABASE_DB_URL` e `VOYAGE_API_KEY`) depois das migrações, para gravar a Base global v1 com embeddings.
- [ ] Confirmar que nenhum Custom Access Token Hook está ativo e ativar `doctor.custom_access_token_hook`.
- [ ] Incluir as URLs do app web nas URLs de redirecionamento do Auth.
- [ ] Confirmar que o Realtime está ligado no projeto. A migração do ticket #16 só acrescenta `doctor.connectors` à publicação `supabase_realtime`, que é do projeto inteiro: conferir antes que a publicação não é `FOR ALL TABLES` e o que o jayv-coder já publica.
- [ ] Confirmar que o schema `doctor` **não** está em "Exposed schemas" da API de dados (PostgREST). `anon` executa as funções do token de ingestão (ticket #12), e expor o schema deixaria chamá-las sem passar pela validação da API. O worker valida de novo, mas a porta certa é só a API.

## App web

- [ ] Definir onde o Next.js roda em produção (ainda sem ticket próprio de deploy) e as variáveis `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_SITE_URL` e `API_URL`.
