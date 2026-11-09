# Piloto da v0.1

Ticket #35. Roteiro da implantação piloto e da medição. O relatório final é o [report.md](report.md).

## Implantação

1. **Organização piloto** criada pelo Owner do cliente, com os membros convidados ([guia](../guia/primeiros-passos.md)) e a linha de base do MTTR: a média das 4 semanas anteriores, informada pelo cliente, em `tenants.mttr_baseline_minutes`. O Dashboard compara com ela.
2. **Conector GCP** configurado para as integrações de produção ([guia](../guia/conector-gcp.md)).
3. **Histórico:** importação dos 100+ incidentes recentes ([guia](../guia/importacao.md)). Eles também formam o dataset real da avaliação (#30, `docs/operations/avaliacao.md`).
4. **Treinamento (1 h):**
   - 10 min: o que o Doctor faz e o que não faz (Recomendação é ação humana; Confiança heurística);
   - 15 min: Integrações, Conector e Importação;
   - 20 min: um Incidente real, do Diagnóstico ao Relatório, com a revisão (**Aceitar**, **Corrigir**, **Rejeitar**);
   - 15 min: perguntas e o combinado da medição (revisar todo Diagnóstico do piloto).

## Medição (4 semanas)

| O quê | Como |
|---|---|
| MTTR no piloto contra a linha de base | Dashboard e `scripts/pilot_report.py` (só Incidentes que começaram no piloto: o histórico importado fica de fora) |
| Tempo até a revisão | `diagnosis_feedback.time_to_review_s` (#26) |
| Precisão de categoria e de causa | revisões do piloto (`pilot_report.py`) e a avaliação do #30 sobre os incidentes do piloto |
| Diagnósticos com Evidência rastreável | `pilot_report.py`: publicados com Evidência num registro da própria Organização (a Base global não conta) |
| Vazamentos (meta 0) e correções automáticas (meta 0) | `pilot_report.py`, mais a suíte de isolamento do CI (#27) |
| Usabilidade (SUS) com ≥ 5 usuários, incluindo o celular | questionário [sus.md](sus.md) e `scripts/sus_score.py` |

```bash
# datas em UTC
SUPABASE_DB_URL=… uv run python scripts/pilot_report.py <tenant_id> \
  --since 2026-11-10 --until 2026-12-08 --sus respostas-sus.csv > numeros.md
```

O script sai com código 1 se houver vazamento ou correção automática.

## Feedback

Toda observação dos usuários (entrevista no fim da semana 2 e da semana 4, comentários no app) vira uma issue com o rótulo `v0.2` e `feedback-piloto`, com a tela, o que a pessoa tentou fazer e o que esperava. Nenhum dado de cliente vai para a issue: use o id do Incidente, nunca o conteúdo do log.
