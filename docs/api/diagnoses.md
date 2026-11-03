# Diagnóstico

Exigem `Authorization: Bearer <JWT do Supabase Auth>` e Organização ativa. Todo Papel lê; Analyst ou acima pede; Owner ou Admin com MFA (`aal2`) liga o Diagnóstico automático. O banco confere o Papel de novo na tabela.

| Rota | Efeito |
|---|---|
| `POST /api/v1/incidents/{id}/diagnoses` | `{ mode: "hybrid" \| "rules_only", include_knowledge_base }` com `Idempotency-Key` → `202 { diagnosis_id, status: "queued", version }` |
| `GET /api/v1/incidents/{id}/diagnoses` | Versões do Diagnóstico do Incidente, da mais nova para a mais antiga |
| `GET /api/v1/diagnoses/{id}` | Diagnóstico com Hipóteses, Evidências, Recomendações e `verification_notes` |
| `POST /api/v1/diagnoses/{id}/feedback` | `{ verdict: "accepted" \| "corrected" \| "rejected", correct_category?, correct_cause?, responsible_system?, comment? }` → `201` (Analyst ou acima, um por revisor por versão) |
| `POST /api/v1/incidents/{id}/knowledge` | Promove o Incidente resolvido, com a versão mais nova aceita ou corrigida, à Base de conhecimento → `201 { document_id }` |
| `GET` / `PUT /api/v1/settings/diagnosis` | `{ auto_diagnose_critical }`: Diagnóstico híbrido automático ao abrir Incidente crítico (desligado por padrão) |

- **Assíncrono:** o pedido entra na fila (`diagnosis.requested`) e o worker de diagnóstico roda as 6 etapas. `stage` avança (`validation`, `correlation`, `rules`, `knowledge`, `llm`, `verification`, `done`) e chega à tela pelo Realtime (`doctor.diagnoses` está na publicação `supabase_realtime`). Ao publicar, sai `diagnosis.published`.
- **Idempotência:** a `processing_key` do Diagnóstico (`unique (tenant_id, processing_key)`) é o hash de Usuário, Incidente, corpo e `Idempotency-Key`: a mesma requisição devolve o mesmo Diagnóstico, mesmo depois das 24 h da resposta gravada, e duas pessoas com a mesma chave não se cruzam. Entregas repetidas da mensagem não fazem outro: o worker toma posse (`queued` → `running`, por 5 min) e quem chega depois ignora.
- **Falhas do worker:** falha de banco, rede ou código devolve o Diagnóstico à fila para a próxima entrega; na terceira tentativa ele vira `failed`, com `error`, `published_at` e a mensagem `diagnosis.published`, como os outros finais.
- **Versões:** cada pedido é a versão N+1 do Incidente. Publicado (`published`, `inconclusive`, `failed_llm` ou `failed`), o Diagnóstico e as filhas não mudam (trigger, erro `DR020`). Só as FKs da retenção e da exclusão de Usuário zeram referências.
- **Status:** `published` tem ao menos uma Evidência rastreável; `inconclusive` = Evidências insuficientes (a tela não mostra a Causa provável como fato); `failed_llm` = o LLM falhou e o resultado veio só das Regras; `failed` = o Diagnóstico não pôde rodar (`error`).
- **Modo:** `requested_mode` é o pedido, `mode` o efetivo. `rules_only` pula a Base de conhecimento e o LLM; o híbrido cai nele quando a Cota de IA acaba (#31) ou o LLM falha, com a nota em `verification_notes`.
- **Verificação (etapa 6):** Evidência citada pelo LLM que não é dado do Incidente (nem de outra Organização, que nunca entra no contexto) é descartada e registrada; sem Evento nem Regra do próprio Incidente entre as Evidências (só a Base de conhecimento não basta), `inconclusive`; a Confiança cai com Evidência descartada (×0,85) ou só fraca (no máximo 0,4); Recomendação que sugira ação automática é bloqueada; Sistema responsável fora da Integração vira indeterminado (`null`). As Hipóteses recebem os mesmos ajustes de Confiança.
- **Base de conhecimento na etapa 4:** sem embedding (provedor fora), a busca segue só pelo texto.
- **Confiança:** heurística, não calibrada. Mostre sempre com esse rótulo.
- **Evidência:** `kind` (`event`, `rule_match`, `chunk`, `global_chunk`), `ref_id` (nulo se a retenção já apagou o registro), `label` (o que o registro era) e `finding`.
- **Revisão humana (#26):** corrigir exige a categoria ou a causa certa. Aceite ou correção tira o "Requer revisão" (a única mudança que a versão publicada aceita). `time_to_review_s` guarda o tempo da publicação à revisão. A Trilha de auditoria registra `diagnosis.reviewed` com quem revisou (`actor_id`), o veredito e a versão (`after`). Só a versão publicada mais nova recebe revisão (ADR-0013). Erros: `422 correction_required`, `409 already_reviewed`, `409 not_reviewable` (versão em andamento ou com falha), `409 superseded` (há versão mais nova).
- **Promover (#26):** cria um documento `source = 'incident'` com a classificação e a causa (a correção vale sobre o Diagnóstico), as Evidências e a resolução; o worker sanitiza antes de fragmentar e troca o texto do registro pelo sanitizado (os membros não leem a coluna `body`), e o Diagnóstico de um Incidente semelhante o recupera na etapa 4. Um por Incidente; `IncidentDetail.promotable` diz se a promoção é possível, pela mesma regra. Erros: `409 not_resolved`, `409 not_reviewed`, `409 already_promoted`.
