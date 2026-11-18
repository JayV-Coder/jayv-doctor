"""Engine do Supavisor: sem pool por padrão (GCP, ADR-0009); com DB_POOL_SIZE, reaproveita
conexões, o que importa quando o banco está longe (Railway nos EUA, banco em São Paulo)."""

import pytest
from aid_db import supavisor_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

URL = "postgresql://u:p@db.test:6543/postgres"


def test_sem_db_pool_size_nao_guarda_conexoes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DB_POOL_SIZE", raising=False)
    assert isinstance(supavisor_engine(URL).pool, NullPool)


def test_com_db_pool_size_guarda_conexoes_sem_teto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", "4")
    pool = supavisor_engine(URL).pool
    assert isinstance(pool, AsyncAdaptedQueuePool)
    assert pool.size() == 4
    # Acima das guardadas, abre extras como o NullPool: nenhum pedido espera na fila do pool.
    assert pool._max_overflow == -1


@pytest.mark.parametrize("value", ["0", "", "abc", "-2"])
def test_valor_invalido_ou_zero_fica_sem_pool(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DB_POOL_SIZE", value)
    assert isinstance(supavisor_engine(URL).pool, NullPool)


@pytest.mark.asyncio
async def test_papel_desconhecido_nao_chega_ao_banco() -> None:
    from aid_db import session_settings

    with pytest.raises(ValueError, match="papel inesperado"):
        await session_settings(None, "postgres")  # type: ignore[arg-type]
