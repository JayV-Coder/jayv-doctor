# Revisão humana muda só o "Requer revisão" do Diagnóstico publicado

O invariante do projeto é que Diagnóstico publicado é imutável: nova análise é nova versão (trigger `DR020` em `doctor.diagnoses` e nas filhas). A revisão humana (#26) pede um efeito na versão revisada: depois do aceite ou da correção, ela não "Requer revisão".

Gravar esse estado em outra tabela obrigaria toda leitura a cruzar com o feedback para saber se a versão ainda pede revisão. Por isso o trigger aceita uma única mudança além das FKs: `requires_human_review` de `true` para `false`, feita por `doctor.submit_diagnosis_feedback`. O conteúdo do Diagnóstico (causa, Confiança, Evidências, Hipóteses e Recomendações) continua intocável, e o que a pessoa corrigiu fica no próprio `diagnosis_feedback`, nunca sobrescrito no Diagnóstico.

## Consequências

- `requires_human_review` só desce: a versão não volta a "Requer revisão" (o trigger recusa `false` → `true`), e uma revisão discordante é outro feedback, não uma edição.
- A tela mostra o veredito pelo feedback (correção, depois aceite, depois recusa) e a causa corrigida mais recente; a promoção à Base usa a mesma escolha.
- Só a versão mais nova publicada recebe revisão: feedback de versão superada inflaria as métricas de precisão e de tempo até a revisão do piloto (#30).
- As outras exceções do trigger são de FK: a retenção zerando a referência de uma Evidência e a exclusão do Usuário que pediu (`requested_by`).
