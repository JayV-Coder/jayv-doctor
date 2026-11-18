"""Atributos que o handler recebe de uma mensagem do RabbitMQ: os mesmos do Pub/Sub, sem os
cabeçalhos do broker nem o da tentativa."""

from types import SimpleNamespace
from typing import Any, cast

from aid_worker.rabbit import attributes_of


def message(headers: dict[str, Any]) -> Any:
    return cast(Any, SimpleNamespace(headers=headers))


def test_so_os_atributos_da_outbox_chegam_ao_handler() -> None:
    headers = {
        "tenant_id": "t",
        "outbox_id": "7",
        "traceparent": b"00-abc",
        "x-aid-attempt": 2,
        "x-first-death-reason": "expired",
        "x-death": [{"queue": "aid.retry.10s"}],
        "x-delivery-count": 1,
    }
    assert attributes_of(message(headers)) == {
        "tenant_id": "t",
        "outbox_id": "7",
        "traceparent": "00-abc",
    }


def test_valor_que_nao_e_texto_fica_de_fora() -> None:
    assert attributes_of(message({"flag": True, "n": 3, "ok": "sim"})) == {"ok": "sim"}
