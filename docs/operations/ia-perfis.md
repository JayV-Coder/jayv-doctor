# Perfis de IA (ticket #45)

Decisão em [ADR-0018](../adr/0018-perfis-de-ia-por-organizacao.md). Rotas em [docs/api/privacy.md](../api/privacy.md); a tela é **Mais → LGPD e IA → Perfil de IA** e **Subprocessadores**.

| Perfil | Quem liga | Geração | Embeddings | Região |
|---|---|---|---|---|
| `standard` | Owner com MFA | Claude (Anthropic) | Voyage | EUA |
| `br_region` | Owner com MFA | Gemini (Vertex AI) | `text-embedding-005` | `southamerica-east1` |
| `dedicated` | Operação da plataforma | Gemini (Vertex AI) com Provisioned Throughput | `text-embedding-005` | `southamerica-east1` |

## Ligar o dedicado

1. Contrate a capacidade (Provisioned Throughput do Gemini) em `southamerica-east1`, no projeto da plataforma ou no do cliente.
2. No projeto do cliente: conceda `roles/aiplatform.user` à conta de serviço do `worker-diagnosis` e da API.
3. Com `service_role`: `select doctor.set_dedicated_ai('<tenant>', '<projeto do cliente ou null>');` A troca fica na trilha de auditoria (`org.ai_profile_changed`).
4. Force o job `ai-verify` e confira `doctor.ai_profile_checks` (`profile = 'dedicated'`, `target` = projeto).

No dedicado, a geração manda `X-Vertex-AI-LLM-Request-Type: dedicated`: só a capacidade provisionada atende. Sem capacidade, o Vertex responde 429 e o Diagnóstico degrada para `rules_only`. Ele nunca transborda para a capacidade compartilhada. O Owner pode sair do dedicado pela tela.

## O que comprova que o Brasil fica no Brasil

- **Barreira:** o `VertexProvider` só aceita `southamerica-east1` e só fala com `southamerica-east1-aiplatform.googleapis.com` e com o servidor de metadados. Outro host é recusado antes de sair (`ai.egress_blocked`).
- **Logs de egress:** toda chamada de IA registra `ai.egress` com `provider`, `host` e `region`, sem conteúdo. Consulta no Logs Explorer: `jsonPayload.message="ai.egress" AND jsonPayload.provider=~"^vertex"`.
- **Verificação diária:** o job `ai-verify` (06:15 UTC) chama cada perfil em uso com uma pergunta fixa e grava hosts, região e `in_region` em `doctor.ai_profile_checks`. A tela mostra a última. Falha da chamada com os hosts no lugar do perfil (cota, 429 do dedicado) é indisponibilidade (`ok = false`, `in_region = true`, log `ai.profile_check_failed`), não divergência de região.
- **Alerta:** `IA fora da região do perfil` ([runbook](runbooks/ia-regiao.md)).

## Troca de perfil e reindexação

A troca pede confirmação na tela, que diz o que muda (e, saindo do dedicado, que só a operação o liga de novo). Trocar entre `standard` e um perfil do Brasil troca o modelo de embedding. A varredura de hora em hora (`POST /knowledge/reindex`) põe os documentos na fila e a tela mostra "Reindexando a Base: X de Y". Até terminar, a busca (API e RAG do Diagnóstico) também consulta o índice antigo, **se o perfil novo permite**:

- `br_region` ou `dedicated` → `standard`: o índice antigo do Vertex segue consultado;
- `standard` → `br_region` ou `dedicated`: o índice do Voyage **não** é consultado (a pergunta não vai aos EUA). Os Fragmentos antigos seguem achados pelo texto.

## Avaliação por perfil

```bash
uv run python -m aid_evaluation run --modes hybrid --profile standard --judge --judge-provider anthropic --json tests/evaluation/reports/standard.json
uv run python -m aid_evaluation run --modes hybrid --profile br_region --judge --judge-provider anthropic --json tests/evaluation/reports/br_region.json
uv run python -m aid_evaluation compare standard=tests/evaluation/reports/standard.json br_region=tests/evaluation/reports/br_region.json
```

O juiz é o mesmo nos dois (`--judge-provider`, obrigatório com `--profile` e `--judge`): a diferença na Causa provável é do modelo avaliado, não do juiz. O `compare` gera `tests/evaluation/reports/perfis-<data>.md` com a precisão (em p.p.), o custo por Diagnóstico e a latência p95 de cada perfil contra o primeiro. Publique o relatório em [avaliacao.md](avaliacao.md) a cada mudança de modelo.
