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
- [ ] Agente local (#39): publicar a imagem `aid-agent` no registro (`ghcr.io/jayv-coder/aid-agent`) a cada release; gerar a CA de agentes e a chave de release (Ed25519) no Secret Manager (`AID_AGENT_CA_KEY`, `AID_AGENT_CA_CERT`) e definir `AID_PUBLIC_API_URL` e `AID_AGENT_RELEASE` na API; decidir se o mTLS no balanceador entra (ADR-0015). Testar com um SAP de homologação do piloto: usuário técnico com o mínimo privilégio de `docs/operations/agente.md`, a função `Z_AID_…` de SLG1/SM58 e a biblioteca RFC numa imagem derivada; rodar o agente 2 h sem rede e conferir o reenvio sem duplicar.
- [ ] Alertas (#41): gerar as chaves VAPID ([alertas.md](alertas.md)) e pôr a privada no segredo `vapid-private-key` e a pública em `vapid_public_key` no tfvars; conferir `SMTP_URL` no `notifier`; criar um app do Slack com Incoming Webhook e um webhook do Teams (Workflows) de teste; medir no celular do plantão (Android e iPhone 16.4+ com o PWA instalado) que o push de um Incidente crítico em prd chega em menos de 60 s.
- [ ] Webhooks (#42): cadastrar um webhook de teste apontando para um receptor do piloto (ou um RequestBin HTTPS), conferir a assinatura com o exemplo de docs/api/webhooks.md e o "Reenviar"; conferir que o egress do Cloud Run sai pela VPC com NAT (a guarda de SSRF confere o IP; o firewall é a segunda camada).
- [ ] Jira (#43): criar o app OAuth 2.0 (3LO) da plataforma em developer.atlassian.com, com os escopos de [itsm.md](itsm.md) e a callback `<APP_URL>/chamados/jira`; pôr o Client ID em `atlassian_client_id` e o secret em `atlassian-client-secret`. Testar com um site Jira de teste: conexão, chamado manual e por Regra (uma vez só), webhook dinâmico (conferir se chega e se renova), status `done` e comentários com `#doctor` e `#jira`.
- [ ] ServiceNow (#44): numa instância de teste (PDI), registrar o app OAuth com Client Credentials e o usuário de integração (`itil`), conectar em Chamados (ITSM), criar a Business Rule de [itsm.md](itsm.md) com o endereço mostrado e conferir: incident de um Diagnóstico com Sistema "SAP" no grupo mapeado, "Indeterminado" no grupo padrão, uma vez só (à mão e por Regra), e o status Resolvido voltando ao Incidente.
- [ ] Perfis de IA (#45): no projeto de produção, habilitar o Vertex AI em `southamerica-east1` e conferir que a conta de serviço do `worker-diagnosis` e da API tem `roles/aiplatform.user`; forçar o job `ai-verify` e ver `ok` em `doctor.ai_profile_checks` para `standard` e `br_region`; trocar uma Organização de teste para `br_region` e conferir no Logs Explorer que todo `ai.egress` do período é de `southamerica-east1` (o critério do ticket), o reindex da Base e o alerta `IA fora da região do perfil` (forçando um `ai.egress_blocked` num ambiente de teste). Dedicado: só com capacidade contratada ([ia-perfis.md](ia-perfis.md)).
- [ ] Correlação entre sistemas e enriquecimento (#40): com o piloto, montar o Mapa do fluxo real (campos de cada sistema e transformações) e conferir na Timeline as raias numa Execução; criar o Conector OData do S/4 (ou ECC pelo gateway/BTP) com usuário técnico só de leitura em `API_SALES_ORDER_SRV`, ou usar o Conector Salesforce, e conferir o Diagnóstico de um 504 com o pedido criado ("não reenviar"). Conferir que o serviço OData do cliente resolve para IP público (a guarda de SSRF recusa rede interna).
- [ ] Decidir e montar a identidade de plataforma por Organização, que liga o modo sem chave (`impersonation`) do conector GCP (ver `docs/operations/conectores.md`).

## Supabase hospedado (exige aprovação na hora, ADR-0009)

- [ ] `scripts/apply-doctor-migrations.py --check` e, na janela combinada, `--apply`. As migrações criam o schema `doctor`, o bucket `doctor-raw-logs` e as políticas dele em `storage.objects`.
- [ ] Extensão `vector` (pgvector, ticket #23): a migração da Base de conhecimento a cria no schema `extensions`. Instalar extensão no projeto compartilhado exige aprovação na janela; conferir antes se o jayv-coder já a usa. A busca usa `hnsw.iterative_scan` (pgvector ≥ 0.8): conferir a versão (`select extversion from pg_extension where extname = 'vector'`).
- [ ] Conector Salesforce (#37): criar a Connected App na org do cliente (JWT Bearer com certificado, usuário de integração pré-autorizado, escopo `api`/`refresh_token`) e testar contra uma org real (sandbox primeiro): fontes, Checkpoint, a pausa a 80% do limite e a mensagem de EventLogFile numa edição sem Event Monitoring.
- [ ] SAP (#38): conferir os presets de importação com exportações reais da SM58, SLG1 e WE02 do cliente (os nomes de coluna variam por idioma e layout de ALV); testar o conector do Integration Suite numa subconta BTP (service key do plano `api` com `MonitoringDataRead`).
- [ ] Relatório técnico (#32): conferir o PDF gerado no Cloud Run (fontes e acentos, imagem com `SYSTEM_PACKAGES`); `APP_URL` da API apontando para o app (o link compartilhável usa `{APP_URL}/compartilhado#…`); o bucket `doctor-reports` é criado pela migração no projeto compartilhado.
- [ ] Piloto (#35): habilitar o GitHub Pages (Settings → Pages → GitHub Actions) para a documentação da API; criar a Organização piloto, informar `mttr_baseline_minutes`, configurar o Conector GCP, importar os 100+ incidentes e dar o treinamento ([roteiro](../pilot/README.md)); aplicar o SUS e preencher `docs/pilot/report.md` com `scripts/pilot_report.py`.
- [ ] Observabilidade (#34): preencher `alert_emails`, `oncall_webhook_url` (canal de plantão) e `platform_operators` no tfvars; conferir o primeiro trace de ponta a ponta no Cloud Trace e a CPU do Supabase no dashboard (Metrics API com a chave de serviço do projeto compartilhado); disparar um alerta de teste por canal.
- [ ] Carga e backup (#33): rodar `make load:*` em staging e preencher a tabela de Resultados de `capacity.md` (um ticket por meta não atingida); habilitar o PITR no projeto (add-on, decisão com o jayv-coder) e fazer o drill de `runbooks/restore.md`, registrando RTO e RPO; definir com o jayv-coder a fatia de clientes do Supavisor (`supavisor_client_budget`) e o `pool_size`; conferir o primeiro backup do Storage no bucket `<projeto>-storage-backup`.
- [ ] Cotas (#31): `AID_LLM_PRICES` no worker de diagnóstico (tabela oficial de preços por modelo) para o custo estimado; o segredo `smtp-url` também no worker de diagnóstico (avisos de Cota); conferir os limites do plano piloto com o cliente antes de ligar a imposição.
- [ ] Avaliação (#30): ≈ 40 casos reais anonimizados do cliente piloto, com autorização, rotulados por especialista (`python -m aid_evaluation label`); `tests/evaluation/prices.json` com a tabela oficial de preços; `ANTHROPIC_API_KEY` e `VOYAGE_API_KEY` como segredos do repositório para a avaliação semanal; rodar `make eval-hybrid` e publicar o relatório com o híbrido.
- [ ] LGPD (#29): revisão jurídica dos modelos em `docs/lgpd/` (DPA, RIPD, transferência internacional, resposta a incidentes) e preenchimento dos campos entre colchetes; conferir a região do projeto Supabase na lista de subprocessadores. Depois de cada exclusão total no ambiente real, rodar `scripts/verify_tenant_deleted.py`.
- [ ] Auditoria (#28): conferir, no projeto real, os nomes das ações de MFA em `auth.audit_log_entries` (o mapeamento em `doctor.import_auth_events` usa `login`, `logout`, `factor_*` e `mfa_code_login`) e se o projeto grava o IP nesses eventos.
- [ ] Segurança (#27): rodar os Advisors do Supabase (security e performance) no projeto e conferir que assinar `doctor.diagnoses` de outra Organização pelo Realtime não entrega eventos (o CI sobe sem Realtime). Ver `docs/security/isolamento-e-asvs-l2.md`.
- [ ] Diagnóstico (#24): a Cota de IA ainda libera tudo (`ai_allowed` no worker de diagnóstico); o controle de consumo entra com o #31 (`usage_records`, `usage_llm`).
- [ ] Rodar `python -m aid_knowledge.global_seed` (com `SUPABASE_DB_URL` e `VOYAGE_API_KEY`) depois das migrações, para gravar a Base global v1 com embeddings.
- [ ] Confirmar que nenhum Custom Access Token Hook está ativo e ativar `doctor.custom_access_token_hook`.
- [ ] Incluir as URLs do app web nas URLs de redirecionamento do Auth.
- [ ] Confirmar que o Realtime está ligado no projeto. A migração do ticket #16 só acrescenta `doctor.connectors` à publicação `supabase_realtime`, que é do projeto inteiro: conferir antes que a publicação não é `FOR ALL TABLES` e o que o jayv-coder já publica.
- [ ] Confirmar que o schema `doctor` **não** está em "Exposed schemas" da API de dados (PostgREST). `anon` executa as funções do token de ingestão (ticket #12), e expor o schema deixaria chamá-las sem passar pela validação da API. O worker valida de novo, mas a porta certa é só a API.

## App web

- [ ] Definir onde o Next.js roda em produção (ainda sem ticket próprio de deploy) e as variáveis `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_SITE_URL` e `API_URL`.
