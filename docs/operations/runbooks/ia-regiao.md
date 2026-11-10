# Alerta: IA fora da região do perfil

**Disparo:** um dos logs abaixo apareceu (alerta por log, no máximo um aviso a cada 5 min):

- `ai.profile_divergence`: a verificação diária (`POST /ai/verify` no `worker-diagnosis`) viu hosts ou região diferentes do perfil, ou a chamada de teste falhou;
- `ai.egress_blocked`: um provedor do Vertex tentou falar com um host fora do Brasil e foi barrado antes de sair;
- `ai.egress` de um provedor `vertex*` com `region` fora de `southamerica-east1`.

Nos dois primeiros casos nada saiu do Brasil: o provedor recusa o host. O terceiro não deveria acontecer e é incidente de privacidade.

1. **Qual perfil e projeto:** `jsonPayload.profile` e `jsonPayload.target` (ou `provider` e `host`) no Logs Explorer; o histórico está em `doctor.ai_profile_checks` (`order by checked_at desc`).
2. **Divergência por falha da chamada** (`detail` começa com "a chamada falhou"): credencial do Vertex, cota ou Provisioned Throughput sem capacidade (429 no dedicado). Os Diagnósticos seguem em `rules_only`; veja [llm-erros.md](llm-erros.md).
3. **Host ou região diferente:** mudança de código ou de configuração do provedor (`aid_diagnosis_engine/llm/vertex.py`, `GCP_PROJECT_ID`, `ai_project`). Reverta o deploy e abra um incidente de privacidade com o DPO: para quais Organizações e quantas chamadas (`ai.egress` no período).
4. Depois de corrigir, rode `POST /ai/verify` de novo (job `ai-verify` no Cloud Scheduler, "Forçar execução") e confira o `ok` em `doctor.ai_profile_checks`.
