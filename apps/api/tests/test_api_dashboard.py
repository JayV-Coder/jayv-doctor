from aid_api.dashboard.service import change, error_rate


def test_taxa_de_erro_sem_execucoes_nao_e_zero() -> None:
    assert error_rate(0, 0) is None
    assert error_rate(200, 7) == 0.035


def test_variacao_sem_base_nao_existe() -> None:
    assert change(120, 100) == 0.2
    assert change(66, 100) == -0.34
    assert change(10, 0) is None
    assert change(None, 100) is None
    assert change(10, None) is None
