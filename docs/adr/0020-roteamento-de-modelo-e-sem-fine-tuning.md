# Modelo por complexidade, decidido pela avaliação, e sem fine-tuning por enquanto

O custo do Diagnóstico cai muito se os casos simples usarem o modelo menor (`claude-haiku-5-5`, Gemini Flash ou um open-weights de 8 a 70B). O risco é perder precisão justamente onde a IA mais ajuda. A decisão de trocar não é de gosto: é da avaliação (#30).

**Roteamento.** O motor escolhe o modelo do caso, **por perfil de IA** (`AID_LLM_ROUTING`, mapa `llm_routing` do Terraform, ex. `{ standard = "by_complexity" }`). Perfil fora do mapa fica em `fixed`, e o `dedicated` só entra no mapa com capacidade contratada para o modelo menor (sem ela, o Vertex responde 429):

- `fixed` (padrão): sempre o modelo maior, como até aqui;
- `by_complexity`: o menor quando as Regras já explicam o caso (uma categoria só entre as Regras que dispararam, conhecida e igual à do Incidente, até 30 Eventos); o maior quando não há Regra, quando há categorias em conflito ou quando há muitos Eventos;
- `classify_first`: o menor classifica (categoria e confiança heurística); se concordar com o Incidente com confiança de 0,7 ou mais, ele mesmo interpreta, senão a interpretação vai ao maior. É a separação "classificação no menor, interpretação no maior";
- `fast`: sempre o menor.

**Critério para mudar o padrão.** `aid_evaluation compare` põe a recomendação no relatório: adotar só se o custo médio por Diagnóstico cair ao menos 30%, nenhuma das duas precisões (categoria e Causa provável) cair mais de 2 p.p. e as falhas do LLM não subirem mais de 2 p.p. As duas variantes precisam ter rodado nos mesmos casos e com o mesmo juiz. Sem isso, o relatório diz por que não. A recomendação vale por perfil de IA (ADR-0018): o mesmo roteamento pode passar no `standard` e falhar no `br_region`.

**Fine-tuning.** Não neste momento. O PRD exclui treinar modelos próprios no início; o roteamento e a escolha de modelo se medem com o harness que já existe, e um fine-tuning exigiria dados rotulados em volume, custo de treino e uma avaliação a cada versão. Ele só volta à mesa se a avaliação mostrar que nenhum modelo pronto atinge o critério acima e que o ganho esperado justifica o custo, com uma nova ADR.

## Consequências

- O padrão continua `fixed` até a primeira avaliação real (com chaves de produção e o dataset rotulado), registrada em `docs/operations/avaliacao.md`.
- Mudar o roteamento é mudar uma variável e fazer o deploy, sem migração; cada Diagnóstico registra o modelo que usou.
- O perfil `local` (ADR-0019) usa o único modelo servido no cliente; o roteamento não muda nada para ele.
