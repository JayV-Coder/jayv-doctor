"""Fusão das buscas vetorial e textual (Reciprocal Rank Fusion): cada lista vota pela posição,
sem precisar comparar a escala dos scores de uma com a da outra."""

from collections import defaultdict
from collections.abc import Hashable, Sequence

K = 60


def rrf[T: Hashable](rankings: Sequence[Sequence[T]], k: int = K) -> list[T]:
    scores: dict[T, float] = defaultdict(float)
    first_seen: dict[T, int] = {}
    order = 0
    for ranking in rankings:
        for position, item in enumerate(ranking):
            scores[item] += 1 / (k + position + 1)
            if item not in first_seen:
                first_seen[item] = order
                order += 1
    return sorted(scores, key=lambda item: (-scores[item], first_seen[item]))
