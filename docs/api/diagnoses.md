# Diagnóstico

Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. Todo Papel lê; Analyst ou acima pede; Owner ou Admin liga o Diagnóstico automático. O banco confere o Papel de novo na tabela.

| Rota | Efeito |
|---|---|
| `POST /api/v1/incidents/{id}/diagnoses` | `{ mode: "hybrid" \| "rules_only", include_knowledge_base }` com `Idempotency-Key` → `202 { diagnosis_id, status: "queued", version }` |
| `GET /api/v1/incidents/{id}/diagnoses` | Versões do Diagnóstico do Incidente, da mais nova para a mais antiga |
| `GET /api/v1/diagnoses/{id}` | Diagnóstico com Hipóteses, Evidências, Recomendações e `verification_notes` |
| `GET` / `PUT /api/v1/settings/diagnosis` | `{ auto_diagnose_critical }`: Diagnóstico híbrido automático ao abrir Incidente crítico (desligado por padrão) |

- **Assíncrono:** o pedido entra na fila (`diagnosis.requested`) e o worker de diagnóstico roda as 6 etapas. `stage` avança (`validation`, `correlation`, `rules`, `knowledge`, `llm`, `verification`, `done`) e chega à tela pelo Realtime (`doctor.diagnoses` está na publicação `supabase_realtime`). Ao publicar, sai `diagnosis.published`.
- **Idempotência:** a `Idempotency-Key` vira a `processing_key` do Diagnóstico (`unique (tenant_id, processing_key)`): a mesma chave devolve o mesmo Diagnóstico, e entregas repetidas da mensagem não fazem outro (o worker toma posse com `queued` → `running`; quem chega depois ignora).
- **Versões:** cada pedido é a versão N+1 do Incidente. Publicado (`published`, `inconclusive`, `failed_llm` ou `failed`), o Diagnóstico e as filhas não mudam (trigger, erro `DR020`). Só as FKs da retenção e da exclusão de Usuário zeram referências.
- **Status:** `published` tem ao menos uma Evidência rastreável; `inconclusive` = Evidências insuficientes (a tela não mostra a Causa provável como fato); `failed_llm` = o LLM falhou e o resultado veio só das Regras; `failed` = o Diagnóstico não pôde rodar (`error`).
- **Modo:** `requested_mode` é o pedido, `mode` o efetivo. `rules_only` pula a Base de conhecimento e o LLM; o híbrido cai nele quando a Cota de IA acaba (#31) ou o LLM falha, com a nota em `verification_notes`.
- **Verificação (etapa 6):** Evidência citada pelo LLM que não é dado do Incidente (nem de outra Organização, que nunca entra no contexto) é descartada e registrada; sem Evidência válida, `inconclusive`; a Confiança cai com Evidência descartada (×0,85) ou só fraca (no máximo 0,4); Recomendação que sugira ação automática é bloqueada; Sistema responsável fora da Integração vira indeterminado (`null`).
- **Confiança:** heurística, não calibrada. Mostre sempre com esse rótulo.
- **Evidência:** `kind` (`event`, `rule_match`, `chunk`, `global_chunk`), `ref_id` (nulo se a retenção já apagou o registro), `label` (o que o registro era) e `finding`.
