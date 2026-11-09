# Questionário SUS (System Usability Scale)

Versão em português das 10 afirmações do SUS. Notas de 1 (discordo totalmente) a 5 (concordo totalmente). Aplique com pelo menos 5 usuários do piloto, sendo pelo menos 2 no celular, depois de 2 semanas de uso.

1. Eu acho que gostaria de usar o Integration AI Doctor com frequência.
2. Eu achei o sistema desnecessariamente complexo.
3. Eu achei o sistema fácil de usar.
4. Eu acho que precisaria de ajuda de uma pessoa técnica para conseguir usar o sistema.
5. Eu achei que as funções do sistema estão bem integradas.
6. Eu achei que o sistema tem muita inconsistência.
7. Eu imagino que a maioria das pessoas aprenderia a usar o sistema rapidamente.
8. Eu achei o sistema muito complicado de usar.
9. Eu me senti confiante usando o sistema.
10. Eu precisei aprender muitas coisas antes de conseguir usar o sistema.

Anote também: o dispositivo (celular ou computador), o Papel e um comentário livre ("o que mais atrapalhou?"). O comentário vira issue ([README](README.md#feedback)).

## Pontuação

As ímpares valem `nota - 1`, as pares `5 - nota`; a soma vezes 2,5 dá de 0 a 100. A média de mercado é 68.

```bash
# respostas.csv: cabeçalho q1,…,q10 e uma linha por respondente
uv run python scripts/sus_score.py respostas.csv
```
