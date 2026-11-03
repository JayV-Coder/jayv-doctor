# Avaliação do motor de diagnóstico

Ticket #30. Metas do piloto: precisão de categoria ≥ 85% e de Causa provável ≥ 75% (quando há evidência), em ≥ 100 Incidentes históricos, com casos sem causa identificável na conta.

## Dataset

`tests/evaluation/datasets/*.jsonl` (todos entram na avaliação), um caso por linha (`packages/evaluation/src/aid_evaluation/dataset.py`):

- `events`: Eventos já sanitizados e anonimizados, com a Execução de cada um e o instante da avaliação;
- `label`: gabarito do especialista (`category`, `probable_cause`, `responsible_system`, `expected_inconclusive`);
- `source`: `synthetic` (Regra e cenário que o geraram) ou `real` (cliente e autorização).

O sintético (`synthetic-v1.jsonl`) tem **126 casos**: 13 por Regra (INT-001 a INT-008), 4 com dois sinais e 18 sem causa identificável (o arquivo não é editado à mão: sai de `python -m aid_evaluation generate`, que só escreve nele, e um teste confere que o versionado é o que o gerador produz). **Faltam os ≈ 40 casos reais anonimizados do cliente piloto**, que só entram com a autorização dele (ver pendências). Sem eles, o rules_only acerta 100% por construção, porque o sintético nasce das próprias Regras: o número só mostra que as Regras fazem o que documentam.

### Caso real

1. Exportar a Execução do Incidente resolvido (Eventos já sanitizados pela ingestão) e trocar o que identifica o cliente: nomes de sistemas, ids e valores de pedido por fictícios.
2. Adicionar a linha em `tests/evaluation/datasets/real-v1.jsonl` (o gerador nunca toca nele) com `source: {"kind": "real", "client": "<apelido>", "authorized": true}` e sem `label`.
3. Rotular: `uv run python -m aid_evaluation label tests/evaluation/datasets/real-v1.jsonl --who "<especialista>"` (pergunta "sem causa identificável?" ou a categoria (uma das 8), a Causa provável e o Sistema responsável, e repete a pergunta até a resposta ser válida; `--review` revisa os já rotulados). Caso sem gabarito fica fora das métricas, e o relatório avisa.

## Rodar

| Comando | O quê |
|---|---|
| `make eval` | rules_only, sem provedor; relatório em `tests/evaluation/reports/<data>.md` |
| `make eval-hybrid` | rules_only e híbrido com o provedor real (`EVAL_PROVIDER`, padrão `anthropic`) e o juiz LLM da Causa provável |
| `make eval-gate` | o gate do CI: falha se a precisão de categoria ou o inconclusivo correto do rules_only cair mais de 2 p.p. contra `tests/evaluation/baseline.json` (mudança esperada: `python -m aid_evaluation gate --update` na mesma PR) |
| `python -m aid_evaluation sample tests/evaluation/reports/latest-results.jsonl` | 20% dos casos julgados, em CSV, para uma pessoa conferir o juiz |

No CI: o gate roda em toda PR que mexe no motor, no harness ou no dataset (`.github/workflows/evaluation.yml`); a avaliação semanal (segunda, 09:00 UTC) roda o híbrido quando o repositório tem `ANTHROPIC_API_KEY` e guarda o relatório como artefato por 90 dias.

## Métricas

- **Categoria:** no rules_only, a do Incidente (Regras); no híbrido, a classificação do LLM, que só acerta se for uma das 8 categorias (um código próprio, como `UPSTREAM_TIMEOUT`, conta como erro). Precisão sobre os casos com causa e matriz de confusão (com "—" para sem categoria).
- **Falhas do LLM:** casos do híbrido em que o LLM falhou e o Diagnóstico saiu só das Regras (`failed_llm`): contam como erro de categoria e ficam fora da Causa e da alucinação.
- **Causa provável:** juiz LLM (mesma causa raiz?), só no híbrido, nos casos com causa que não saíram inconclusivos; juiz fora deixa o caso sem veredito, sem parar a rodada; 20% conferidos por uma pessoa.
- **Inconclusivo correto:** casos sem causa identificável que saíram `inconclusive`; **inconclusivo indevido:** casos com causa que saíram `inconclusive`.
- **Alucinação de Evidência:** Evidências citadas pelo LLM que a verificação descartou ÷ citadas.
- **Tokens, custo e latência p50/p95:** por modo. O custo usa `tests/evaluation/prices.json` (`{"<modelo>": {"input_per_mtok": …, "output_per_mtok": …}}`), preenchido com a tabela oficial do provedor; sem ele, o custo fica em aberto.

## Calibração da Confiança

A Confiança do Diagnóstico é **heurística** e continua rotulada assim na tela ("Confiança heurística (não calibrada)") enquanto não houver **≥ 500 casos reais rotulados**. Com eles:

1. rodar o híbrido sobre o dataset e agrupar os Diagnósticos por faixa de Confiança (0,1 de largura);
2. comparar, em cada faixa, a Confiança média com a taxa real de Causa provável correta (diagrama de confiabilidade) e medir o erro de calibração esperado (ECE);
3. ajustar o mapeamento (regressão isotônica sobre a Confiança do modelo e os ajustes da verificação) num conjunto separado e validar no restante;
4. só com o ECE abaixo de 5 pontos o rótulo muda, numa PR própria, com o relatório da calibração e uma ADR.
