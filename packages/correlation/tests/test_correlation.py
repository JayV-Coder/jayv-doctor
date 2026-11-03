"""Motor de correlação: agrupamento, estratégias, determinismo e precisão num dataset sintético."""

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from aid_correlation import Correlator, EventRef, Settings, execution_status, merge_plan
from hypothesis import given, settings
from hypothesis import strategies as st

TENANT = "00000000-0000-4000-8000-00000000ac01"
OTHER_TENANT = "00000000-0000-4000-8000-00000000be01"
INTEGRATION = "00000000-0000-4000-8000-0000000001a1"
T0 = datetime(2026, 11, 2, 14, 2, 1, 120000, tzinfo=UTC)


def event(
    number: int, offset_ms: int, severity: str = "INFO", tenant: str = TENANT, **fields: object
) -> EventRef:
    return EventRef(
        id=f"00000000-0000-4000-8000-{number:012d}",
        tenant_id=tenant,
        integration_id=INTEGRATION,
        timestamp=T0 + timedelta(milliseconds=offset_ms),
        severity=severity,
        operation=str(fields.pop("operation", "op")),
        **fields,  # type: ignore[arg-type]
    )


# Tela 8 do mockup: 6 Eventos da exec-123, ligados por execution_id e trace_id.
MOCKUP = [
    event(1, 0, trace_id="trace-abc", operation="outbound_message"),
    event(2, 220, execution_id="exec-123", trace_id="trace-abc", operation="transform"),
    event(3, 282, execution_id="exec-123", operation="BAPI_SALESORDER_CREATE"),
    event(4, 30282, "ERROR", execution_id="exec-123", operation="BAPI_SALESORDER_CREATE"),
    event(5, 30410, "WARNING", execution_id="exec-123", operation="retry_scheduled"),
    event(6, 30412, execution_id="exec-123", operation="sap_confirmation"),
]


def test_os_seis_eventos_do_mockup_fora_de_ordem_formam_uma_execucao_falha() -> None:
    shuffled = MOCKUP[:]
    random.Random(7).shuffle(shuffled)  # noqa: S311 - ordem de teste, não segredo
    (group,) = Correlator().correlate(TENANT, shuffled).groups
    assert len(group.event_ids) == 6
    assert group.duration_ms == 30412
    assert execution_status(group, closed=True) == "failed"
    assert group.correlated_by[MOCKUP[0].id] == "trace_id"
    assert group.correlated_by[MOCKUP[2].id] == "execution_id"
    assert group.keys == {
        "execution_id": ["exec-123"],
        "trace_id": ["trace-abc"],
        "business_reference": [],
    }


def test_referencia_de_negocio_associa_evento_sem_ids_dentro_da_janela() -> None:
    reference = "hmac:9a7b"
    events = [
        event(1, 0, execution_id="exec-1", business_reference=reference),
        event(2, 60_000, business_reference=reference),
        # Fora da janela de 15 min: outra Execução.
        event(3, 16 * 60_000, business_reference=reference),
    ]
    groups = Correlator().correlate(TENANT, events).groups
    first = next(group for group in groups if events[0].id in group.event_ids)
    assert first.correlated_by[events[1].id] == "business_reference"
    assert events[2].id not in first.event_ids


def test_operacao_incompativel_nao_associa_pela_referencia() -> None:
    settings_ = Settings(compatible=lambda a, b: a == b)
    events = [
        event(1, 0, execution_id="exec-1", business_reference="hmac:1", operation="create"),
        event(2, 1000, business_reference="hmac:1", operation="cancel"),
    ]
    assert len(Correlator(settings_).correlate(TENANT, events).groups) == 2


def test_mesmo_trace_em_organizacoes_diferentes_nunca_forma_a_mesma_execucao() -> None:
    events = [event(1, 0, trace_id="t-1"), event(2, 10, trace_id="t-1", tenant=OTHER_TENANT)]
    (group,) = Correlator().correlate(TENANT, events).groups
    assert group.event_ids == (events[0].id,)
    (other,) = Correlator().correlate(OTHER_TENANT, events).groups
    assert other.event_ids == (events[1].id,)


def test_proximidade_temporal_e_fraca_e_marcada() -> None:
    events = [
        event(1, 0, resource="sap-order-sync", attempt=1),
        event(2, 1500, resource="sap-order-sync", attempt=2),
        event(3, 1600, resource="outro", attempt=3),
    ]
    groups = Correlator().correlate(TENANT, events).groups
    weak = next(group for group in groups if events[0].id in group.event_ids)
    assert set(weak.event_ids) == {events[0].id, events[1].id}
    assert weak.low_confidence
    assert weak.correlated_by[events[1].id] == "temporal_proximity"


def test_ids_fortes_diferentes_nao_se_fundem_pela_referencia() -> None:
    events = [
        event(1, 0, execution_id="exec-1", business_reference="hmac:1"),
        event(2, 1000, execution_id="exec-2", business_reference="hmac:1"),
        event(3, 500, business_reference="hmac:1"),
    ]
    groups = Correlator().correlate(TENANT, events).groups
    assert len(groups) == 2
    # O sem ids vai para o mais próximo no tempo; empate desfeito pela chave.
    first = next(group for group in groups if events[0].id in group.event_ids)
    assert events[2].id in first.event_ids


def test_trace_que_chega_depois_funde_duas_execucoes() -> None:
    events = [
        event(1, 0, execution_id="exec-1"),
        event(2, 100, execution_id="exec-2"),
        event(3, 200, execution_id="exec-2", trace_id="t-9"),
        event(4, 300, execution_id="exec-1", trace_id="t-9"),
    ]
    (group,) = Correlator().correlate(TENANT, events).groups
    assert group.keys["execution_id"] == ["exec-1", "exec-2"]


def test_execucao_gravada_nunca_se_divide() -> None:
    # Gravados juntos antes (pela Referência); agora um deles ganha um vizinho forte longe.
    events = [
        event(1, 0, business_reference="hmac:1", execution_ref="x-1"),
        event(2, 60_000, business_reference="hmac:1", execution_ref="x-1"),
        event(3, 61_000, execution_id="exec-9", business_reference="hmac:1"),
    ]
    groups = Correlator().correlate(TENANT, events).groups
    first = next(group for group in groups if events[0].id in group.event_ids)
    assert events[1].id in first.event_ids


def test_estrategia_fraca_nunca_junta_duas_execucoes_ancoradas() -> None:
    # Soltos já gravados em Execuções diferentes; o novo fica entre os dois.
    events = [
        event(1, 0, resource="svc", attempt=1, execution_ref="x-a"),
        event(2, 0, execution_id="exec-1", execution_ref="x-a"),
        event(3, 2000, resource="svc", attempt=3, execution_ref="x-b"),
        event(4, 2000, execution_id="exec-2", execution_ref="x-b"),
        event(5, 1000, resource="svc", attempt=2),
        event(6, 500, business_reference="hmac:1", execution_ref="x-a"),
        event(7, 1500, business_reference="hmac:1", execution_ref="x-b"),
        event(8, 1000, business_reference="hmac:1"),
    ]
    groups = Correlator().correlate(TENANT, events).groups
    assert len(groups) == 2


def test_referencia_sem_id_forte_nao_vira_corrente_sem_fim() -> None:
    # O mesmo pedido reprocessado a cada 10 min por 2 h, sem nenhum id forte.
    events = [event(n, n * 600_000, business_reference="hmac:x") for n in range(1, 13)]
    groups = Correlator().correlate(TENANT, events).groups
    assert all(group.duration_ms <= 15 * 60_000 for group in groups)
    assert len(groups) == 6


def test_plano_de_fusao_mantem_a_execucao_mais_antiga() -> None:
    survivor, merged = merge_plan({"b-exec": T0, "a-exec": T0 + timedelta(seconds=1)})
    assert (survivor, merged) == ("b-exec", ["a-exec"])
    assert merge_plan({}) == (None, [])


def test_status() -> None:
    (group,) = Correlator().correlate(TENANT, [event(1, 0, execution_id="e")]).groups
    assert execution_status(group, closed=False) == "pending_confirmation"
    assert execution_status(group, closed=True) == "success"
    weak = Correlator().correlate(TENANT, [event(1, 0)]).groups[0]
    assert execution_status(weak, closed=True) == "unknown"


def summary(groups: object) -> set[frozenset[str]]:
    return {frozenset(group.event_ids) for group in groups}  # type: ignore[attr-defined]


@settings(max_examples=60, deadline=None)
@given(st.randoms(use_true_random=False))
def test_qualquer_ordem_de_chegada_produz_o_mesmo_resultado(rng: random.Random) -> None:
    events = [*MOCKUP, *SYNTHETIC[:120]]
    expected = Correlator().correlate(TENANT, events)
    shuffled = events[:]
    rng.shuffle(shuffled)
    again = Correlator().correlate(TENANT, shuffled)
    assert again == expected


def synthetic(executions: int, seed: int = 42) -> tuple[list[EventRef], dict[str, int]]:
    """Execuções com gabarito: ids fortes na maioria, Referência ou proximidade no resto."""
    rng = random.Random(seed)  # noqa: S311 - dataset de teste reproduzível
    events: list[EventRef] = []
    truth: dict[str, int] = {}
    number = 1000
    for execution in range(executions):
        start = execution * 45_000 + rng.randint(0, 5_000)
        reference = f"hmac:{execution:08x}"
        kind = rng.random()
        for step in range(rng.randint(2, 7)):
            number += 1
            offset = start + step * rng.randint(50, 900)
            fields: dict[str, Any] = {"business_reference": reference}
            if kind < 0.7:
                fields["execution_id"] = f"exec-{execution}"
            elif kind < 0.9:
                fields["trace_id"] = f"trace-{execution}"
            elif step == 0:
                fields["execution_id"] = f"exec-{execution}"
            else:
                fields = {"resource": f"svc-{execution}", "attempt": step + 1}
                if step > 1:
                    fields["business_reference"] = reference
            severity = "ERROR" if rng.random() < 0.1 else "INFO"
            created = event(number, offset, severity, **fields)
            events.append(created)
            truth[created.id] = execution
    return events, truth


SYNTHETIC, TRUTH = synthetic(1000)


def test_precisao_de_agrupamento_no_dataset_sintetico() -> None:
    groups = Correlator().correlate(TENANT, SYNTHETIC).groups
    correct = 0
    for group in groups:
        executions = [TRUTH[event_id] for event_id in group.event_ids]
        majority = max(set(executions), key=executions.count)
        correct += executions.count(majority)
    precision = correct / len(SYNTHETIC)
    assert precision >= 0.98, precision


def test_cada_execucao_do_gabarito_fica_quase_toda_num_grupo_so() -> None:
    groups = Correlator().correlate(TENANT, SYNTHETIC).groups
    placed: dict[int, list[int]] = {}
    for index, group in enumerate(groups):
        for event_id in group.event_ids:
            placed.setdefault(TRUTH[event_id], []).append(index)
    kept = sum(found.count(max(set(found), key=found.count)) for found in placed.values())
    assert kept / len(SYNTHETIC) >= 0.98, kept / len(SYNTHETIC)
