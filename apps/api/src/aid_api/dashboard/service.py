"""Contas do Dashboard, puras: taxa de erro e variação, com os casos de borda do ticket."""


def error_rate(total: int, failed: int) -> float | None:
    """Sem Execuções no período, não há taxa (e não 0%)."""
    return failed / total if total > 0 else None


def change(current: float | None, previous: float | None) -> float | None:
    """Variação relativa; sem valor ou com base zero, não há comparação."""
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous
