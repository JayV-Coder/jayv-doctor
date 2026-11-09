"""Pontuação do SUS, o questionário de usabilidade do piloto (ticket #35, docs/pilot/sus.md).

Dez afirmações com nota de 1 a 5. As ímpares são positivas (vale a nota - 1) e as pares
negativas (vale 5 - a nota); a soma vezes 2,5 dá de 0 a 100. Acima de 68 é a média de mercado.

CSV: uma linha por respondente, com as colunas q1 a q10 (cabeçalho obrigatório).
Uso: uv run python scripts/sus_score.py respostas.csv
"""

import csv
import io
import sys
from collections.abc import Sequence

QUESTIONS = [f"q{n}" for n in range(1, 11)]


def score(answers: Sequence[int]) -> float:
    if len(answers) != 10 or any(answer not in range(1, 6) for answer in answers):
        raise ValueError("cada respondente tem 10 notas de 1 a 5")
    total = sum(
        answer - 1 if index % 2 == 0 else 5 - answer for index, answer in enumerate(answers)
    )
    return total * 2.5


def read_answers(content: str) -> list[list[int]]:
    rows = csv.DictReader(io.StringIO(content))
    return [[int(row[question]) for question in QUESTIONS] for row in rows]


def mean_score(respondents: Sequence[Sequence[int]]) -> float | None:
    if not respondents:
        return None
    return sum(score(answers) for answers in respondents) / len(respondents)


def main(argv: Sequence[str]) -> int:
    with open(argv[0], encoding="utf-8") as file:
        respondents = read_answers(file.read())
    for index, answers in enumerate(respondents, 1):
        sys.stdout.write(f"respondente {index}: {score(answers):.1f}\n")
    mean = mean_score(respondents)
    sys.stdout.write(f"média ({len(respondents)}): {'—' if mean is None else f'{mean:.1f}'}\n")
    # O checklist pede pelo menos 5 respondentes.
    return 0 if len(respondents) >= 5 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
