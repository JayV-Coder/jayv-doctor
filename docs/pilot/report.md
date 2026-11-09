# Relatório do piloto · v0.1

> **Estado:** modelo. Preenchido ao fim das 4 semanas do piloto ([roteiro](README.md)); os números da seção 1 saem de `scripts/pilot_report.py`.

## 1. Indicadores

| Indicador | Valor | Base |
|---|---|---|
| Precisão de categoria | a medir | Diagnósticos revisados |
| Precisão de causa | a medir | mesma base |
| Diagnósticos com Evidência rastreável | a medir | publicados no período |
| MTTR no piloto | a medir | Incidentes resolvidos |
| MTTR de referência (4 semanas antes) | a informar | cliente |
| Redução de MTTR | a medir | |
| Tempo até a revisão humana | a medir | |
| Vazamentos entre Organizações | a medir | meta 0 |
| Correções automáticas | a medir | meta 0 |
| SUS (usabilidade) | a medir | ≥ 5 usuários |

## 2. Avaliação do motor nos incidentes do piloto

Resultado de `make eval` sobre o dataset rotulado com os incidentes do piloto (`docs/operations/avaliacao.md`): acurácia de categoria, taxa de inconclusivo e, no híbrido, a nota do juiz.

## 3. O que funcionou e o que não funcionou

Resumo das entrevistas e dos comentários, com o link de cada issue `feedback-piloto`.

## 4. Decisão

Liberar a v0.1 (checklist do #36) ou o que falta, com responsável e data.
