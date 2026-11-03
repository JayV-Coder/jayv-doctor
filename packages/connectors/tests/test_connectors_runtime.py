from typing import Any

import pytest
from aid_connectors.base import Batch, Checkpoint
from aid_connectors.fake import FakeConnector
from aid_connectors.runtime import RetryPolicy, run_sync
from aid_connectors.testing import ConnectorContractTests

FAKE_CREDENTIAL = "token-de-teste"


class Sink:
    """Grava lote e Checkpoint juntos, como o worker faz numa transação."""

    def __init__(self, fail_after: int | None = None) -> None:
        self.events: list[dict[str, Any]] = []
        self.checkpoint: Checkpoint | None = None
        self.fail_after = fail_after

    async def __call__(self, batch: Batch) -> None:
        if self.fail_after is not None and len(self.events) >= self.fail_after:
            raise KeyboardInterrupt("worker morreu")
        self.events += batch.events
        self.checkpoint = batch.checkpoint


async def no_sleep(_: float) -> None:
    return None


POLICY = RetryPolicy(attempts=4, base_seconds=0.01, max_seconds=0.05, batch_timeout=0.2)


async def sync(
    config: dict[str, Any], checkpoint: Checkpoint | None = None, sink: Sink | None = None
) -> Any:
    sink = sink or Sink()
    result = await run_sync(
        FakeConnector(), FAKE_CREDENTIAL, config, checkpoint, sink, POLICY, sleep=no_sleep
    )
    return result, sink


@pytest.mark.asyncio
async def test_coleta_todas_as_paginas_e_devolve_o_ultimo_checkpoint() -> None:
    result, sink = await sync({"pages": 3, "page_size": 2})
    assert result.status == "succeeded"
    assert result.records == 6
    assert result.checkpoint_to == {"page": 3}
    assert [event["execution_id"] for event in sink.events] == [
        f"p{p}-{i}" for p in (1, 2, 3) for i in (0, 1)
    ]


@pytest.mark.asyncio
async def test_retoma_do_checkpoint_sem_repetir_paginas() -> None:
    result, sink = await sync({"pages": 3, "page_size": 2}, checkpoint={"page": 2})
    assert result.records == 2
    assert {event["execution_id"] for event in sink.events} == {"p3-0", "p3-1"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "rate_limit", "transient"])
async def test_falha_temporaria_e_repetida_com_backoff_e_retoma_do_checkpoint(failure: str) -> None:
    result, sink = await sync(
        {"pages": 3, "page_size": 1, "fail": {"page": 2, "kind": failure, "times": 2}}
    )
    assert result.status == "succeeded"
    assert result.retries == 2
    assert [event["execution_id"] for event in sink.events] == ["p1-0", "p2-0", "p3-0"]


@pytest.mark.asyncio
async def test_falha_temporaria_que_nao_passa_esgota_as_tentativas() -> None:
    result, sink = await sync(
        {"pages": 3, "page_size": 1, "fail": {"page": 2, "kind": "transient", "times": 99}}
    )
    assert result.status == "failed"
    assert result.error_kind == "transient"
    assert result.checkpoint_to == {"page": 1}
    assert len(sink.events) == 1


@pytest.mark.asyncio
async def test_erro_de_autenticacao_para_na_hora_sem_retry() -> None:
    result, _ = await sync(
        {"pages": 3, "page_size": 1, "fail": {"page": 1, "kind": "auth", "times": 1}}
    )
    assert result.status == "failed"
    assert result.error_kind == "auth"
    assert result.retries == 0


@pytest.mark.asyncio
async def test_paginacao_quebrada_e_detectada() -> None:
    result, _ = await sync({"pages": 3, "page_size": 1, "broken_pagination": True})
    assert result.status == "failed"
    assert result.error_kind == "invalid"
    assert "Checkpoint" in result.error_message


@pytest.mark.asyncio
async def test_lote_que_trava_estoura_o_timeout_e_conta_como_falha_temporaria() -> None:
    result, _ = await sync({"pages": 1, "page_size": 1, "hang_seconds": 5})
    assert result.status == "failed"
    assert result.error_kind == "timeout"


@pytest.mark.asyncio
async def test_queda_do_worker_retoma_do_ultimo_checkpoint_sem_perder_nem_duplicar() -> None:
    sink = Sink(fail_after=2)
    with pytest.raises(KeyboardInterrupt):
        await run_sync(
            FakeConnector(),
            FAKE_CREDENTIAL,
            {"pages": 4, "page_size": 1},
            None,
            sink,
            POLICY,
            sleep=no_sleep,
        )
    assert sink.checkpoint == {"page": 2}
    resumed = Sink()
    await run_sync(
        FakeConnector(),
        FAKE_CREDENTIAL,
        {"pages": 4, "page_size": 1},
        sink.checkpoint,
        resumed,
        POLICY,
        sleep=no_sleep,
    )
    assert [e["execution_id"] for e in sink.events + resumed.events] == [
        "p1-0",
        "p2-0",
        "p3-0",
        "p4-0",
    ]


@pytest.mark.asyncio
async def test_a_credencial_nunca_aparece_no_resultado() -> None:
    result, _ = await sync(
        {"pages": 1, "page_size": 1, "fail": {"page": 1, "kind": "auth", "times": 1}}
    )
    assert FAKE_CREDENTIAL not in repr(result)


class TestFakeConnectorContract(ConnectorContractTests):
    def make_connector(self) -> FakeConnector:
        return FakeConnector()

    def valid_config(self) -> dict[str, Any]:
        return {"pages": 2, "page_size": 2}

    def invalid_config(self) -> dict[str, Any]:
        return {"pages": -1}

    def secret(self) -> str:
        return FAKE_CREDENTIAL


@pytest.mark.asyncio
async def test_retry_after_do_provedor_e_limitado() -> None:
    from aid_connectors.base import ConnectorError

    waits: list[float] = []

    async def record(seconds: float) -> None:
        waits.append(seconds)

    class SlowDown(FakeConnector):
        calls = 0

        async def collect(self, secret: Any, config: Any, checkpoint: Any) -> Any:
            SlowDown.calls += 1
            if SlowDown.calls == 1:
                raise ConnectorError("rate_limit", "429", retry_after=3600)
            async for batch in super().collect(secret, config, checkpoint):
                yield batch

    await run_sync(SlowDown(), FAKE_CREDENTIAL, {"pages": 1}, None, Sink(), POLICY, sleep=record)
    assert waits == [POLICY.max_seconds]


@pytest.mark.asyncio
async def test_prazo_total_encerra_com_o_que_foi_gravado_e_pede_continuacao() -> None:
    clock = iter(range(0, 1000, 10))
    policy = RetryPolicy(
        attempts=4, base_seconds=0.01, max_seconds=0.05, batch_timeout=1, deadline_seconds=25
    )
    sink = Sink()
    result = await run_sync(
        FakeConnector(),
        FAKE_CREDENTIAL,
        {"pages": 10, "page_size": 1},
        None,
        sink,
        policy,
        sleep=no_sleep,
        monotonic=lambda: float(next(clock)),
    )
    assert result.status == "succeeded"
    assert result.more
    assert 0 < result.records < 10
    assert result.checkpoint_to == sink.checkpoint


@pytest.mark.asyncio
async def test_checkpoint_que_volta_a_um_valor_ja_visto_e_paginacao_quebrada() -> None:
    from aid_connectors.base import Batch

    class Cycle(FakeConnector):
        async def collect(self, secret: Any, config: Any, checkpoint: Any) -> Any:
            for cursor in ("a", "b", "a", "b"):
                yield Batch([], {"cursor": cursor})

    result = await run_sync(
        Cycle(), FAKE_CREDENTIAL, {"pages": 1}, None, Sink(), POLICY, sleep=no_sleep
    )
    assert (result.status, result.error_kind) == ("failed", "invalid")
