"""Agrupamento de Eventos em Execuções.

Cada etapa decide só pelo conjunto de Eventos, com desempates por chaves ordenáveis (instante,
id), e nunca pela ordem de chegada: a mesma entrada produz sempre a mesma saída. Os ids fortes
(`execution_id`, `trace_id`) são classes de equivalência. As chaves do Mapa de identificadores
(`cross_keys`, ticket #40) unem Eventos de sistemas diferentes, mesmo com ids fortes diferentes,
quando a mesma chave aparece dentro da janela do mapa: é a configuração explícita da Organização
dizendo que são o mesmo fluxo. A Referência de negócio e a proximidade temporal só prendem
Eventos sem id forte a um grupo, ou entre si, e nunca juntam dois grupos de ids fortes diferentes.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

Strategy = Literal[
    "execution_id", "trace_id", "cross_system", "business_reference", "temporal_proximity"
]
Status = Literal["success", "failed", "pending_confirmation", "unknown"]
FAILED = frozenset({"ERROR", "CRITICAL"})


@dataclass(frozen=True)
class EventRef:
    """O que a correlação precisa de um Evento já normalizado e sanitizado."""

    id: str
    tenant_id: str
    integration_id: str
    timestamp: datetime
    severity: str
    operation: str
    execution_id: str | None = None
    trace_id: str | None = None
    business_reference: str | None = None
    resource: str | None = None
    attempt: int | None = None
    # Chaves do Mapa de identificadores: `<id do mapa>:<valor normalizado>`.
    cross_keys: tuple[str, ...] = ()
    # Execução a que o Evento já pertence (gravada antes): Execuções nunca se dividem, só se
    # juntam, então Eventos com o mesmo `execution_ref` ficam sempre no mesmo grupo.
    execution_ref: str | None = None

    @property
    def order(self) -> tuple[datetime, str]:
        return (self.timestamp, self.id)

    @property
    def strong(self) -> bool:
        return self.execution_id is not None or self.trace_id is not None

    @property
    def anchored(self) -> bool:
        return self.strong or self.execution_ref is not None


def always(_first: str, _second: str) -> bool:
    return True


@dataclass(frozen=True)
class Settings:
    reference_window: timedelta = timedelta(minutes=15)
    proximity: timedelta = timedelta(seconds=2)
    # `operation` compatível para a estratégia da Referência. Por padrão, toda operação da mesma
    # Integração é: a Referência igual dentro da janela já é o sinal.
    compatible: Callable[[str, str], bool] = always
    # Janela de cada Mapa de identificadores (pelo id do mapa, o prefixo da chave).
    cross_windows: Mapping[str, timedelta] = field(default_factory=dict)
    cross_window: timedelta = timedelta(minutes=60)

    def window_of(self, key: str) -> timedelta:
        return self.cross_windows.get(key.split(":", 1)[0], self.cross_window)


@dataclass(frozen=True)
class Group:
    key: str
    tenant_id: str
    integration_id: str
    event_ids: tuple[str, ...]
    severities: tuple[str, ...]
    first_event_at: datetime
    last_event_at: datetime
    correlated_by: Mapping[str, Strategy | None]
    keys: Mapping[str, list[str]]
    low_confidence: bool

    @property
    def duration_ms(self) -> int:
        return round((self.last_event_at - self.first_event_at).total_seconds() * 1000)


@dataclass(frozen=True)
class CorrelationResult:
    groups: tuple[Group, ...]


@dataclass
class _Sets:
    parent: dict[str, str] = field(default_factory=dict)

    def find(self, item: str) -> str:
        root = self.parent.setdefault(item, item)
        while root != self.parent[root]:
            root = self.parent[root]
        while item != root:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, first: str, second: str) -> None:
        a, b = self.find(first), self.find(second)
        if a != b:
            # A menor raiz vence: o resultado não depende da ordem das uniões.
            self.parent[max(a, b)] = min(a, b)


def _gap(first: EventRef, second: EventRef) -> timedelta:
    return abs(first.timestamp - second.timestamp)


def _pairs(bucket: list[EventRef], window: timedelta) -> Iterator[tuple[EventRef, EventRef]]:
    """Pares do balde (já em ordem de instante) a no máximo `window` de distância."""
    for index, event in enumerate(bucket):
        for other in bucket[index + 1 :]:
            if other.timestamp - event.timestamp > window:
                break
            yield event, other


class Correlator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def correlate(self, tenant_id: str, events: Iterable[EventRef]) -> CorrelationResult:
        # Só Eventos da Organização pedida: ids iguais em Organizações diferentes nunca se juntam.
        mine = sorted({e.id: e for e in events if e.tenant_id == tenant_id}.values(), key=_order)
        by_integration: dict[str, list[EventRef]] = defaultdict(list)
        for event in mine:
            by_integration[event.integration_id].append(event)
        groups = [
            group
            for integration in sorted(by_integration)
            for group in self._integration(by_integration[integration])
        ]
        return CorrelationResult(tuple(sorted(groups, key=lambda g: (g.first_event_at, g.key))))

    def _integration(self, events: list[EventRef]) -> list[Group]:
        sets = _Sets()
        how: dict[str, Strategy | None] = {}
        weak: set[str] = set()
        anchors: dict[str, str] = {}
        for event in events:
            sets.find(event.id)
            for kind in ("execution_ref", "execution_id", "trace_id"):
                value = getattr(event, kind)
                if value is not None:
                    sets.union(event.id, anchors.setdefault(f"{kind}:{value}", event.id))
            if event.execution_id is not None:
                how[event.id] = "execution_id"
            elif event.trace_id is not None:
                how[event.id] = "trace_id"
        # Chave do Mapa só ancora quando achou par: um Evento com a chave e sem par continua
        # solto, e a Referência ou a proximidade ainda podem prendê-lo (como antes do Mapa).
        crossed = self._by_cross_keys(events, sets)
        for event_id in crossed:
            how.setdefault(event_id, "cross_system")

        # Ancorado: tem id forte, achou par pelo Mapa ou já pertence a uma Execução gravada. As
        # estratégias fracas só prendem Eventos soltos a um grupo, um de cada vez: nunca ligam
        # dois grupos ancorados.
        loose = [event for event in events if not event.anchored and event.id not in crossed]
        self._by_reference(events, loose, sets, how, crossed)
        self._by_proximity(events, [e for e in loose if e.id not in how], sets, how, weak)

        members: dict[str, list[EventRef]] = defaultdict(list)
        for event in events:
            members[sets.find(event.id)].append(event)
        return [self._group(group, how, weak) for group in members.values()]

    def _by_cross_keys(self, events: list[EventRef], sets: _Sets) -> set[str]:
        """Mesma chave do Mapa, dentro da janela dele: o mesmo fluxo em sistemas diferentes. As
        janelas são fixas a partir do primeiro Evento de cada uma, como na Referência: uma chave
        que se repete a cada 50 min não encadeia Execuções de um dia. Devolve quem achou par."""
        buckets: dict[str, list[EventRef]] = defaultdict(list)
        for event in events:
            for key in event.cross_keys:
                buckets[key].append(event)
        crossed: set[str] = set()
        for key in sorted(buckets):
            window = self.settings.window_of(key)
            head: EventRef | None = None
            for event in buckets[key]:
                if head is None or event.timestamp - head.timestamp > window:
                    head = event
                    continue
                sets.union(event.id, head.id)
                crossed.update((event.id, head.id))
        return crossed

    def _by_reference(
        self,
        events: list[EventRef],
        loose: list[EventRef],
        sets: _Sets,
        how: dict[str, Strategy | None],
        crossed: set[str],
    ) -> None:
        window = self.settings.reference_window
        anchored: dict[str, list[EventRef]] = defaultdict(list)
        spans: dict[str, tuple[datetime, datetime, bool]] = {}
        for event in events:
            if not event.anchored and event.id not in crossed:
                continue
            root = sets.find(event.id)
            first, last, strong = spans.get(root, (event.timestamp, event.timestamp, False))
            spans[root] = (
                min(first, event.timestamp),
                max(last, event.timestamp),
                strong or event.strong or event.id in crossed,
            )
            if event.business_reference is not None:
                anchored[event.business_reference].append(event)

        def fits(event: EventRef, other: EventRef) -> bool:
            first, last, strong = spans[sets.find(other.id)]
            if strong:
                # Ids fortes definem a Execução: basta estar perto de um Evento dela.
                return _gap(event, other) <= window
            # Sem id forte, a Referência sozinha não estica a Execução além da janela.
            return max(last, event.timestamp) - min(first, event.timestamp) <= window

        # Primeiro, cada Evento solto vai para o grupo ancorado mais próximo no tempo. Os vãos
        # são os de antes desta etapa: o resultado não depende da ordem dos soltos.
        chosen: list[tuple[EventRef, str]] = []
        for event in loose:
            if event.business_reference is None:
                continue
            candidates = [
                (_gap(event, other), sets.find(other.id))
                for other in anchored[event.business_reference]
                if self.settings.compatible(event.operation, other.operation) and fits(event, other)
            ]
            if candidates:
                chosen.append((event, min(candidates)[1]))
        for event, root in chosen:
            sets.union(event.id, root)
            how[event.id] = "business_reference"
        # Depois, os que sobraram formam grupos entre si, em janelas fixas a partir do primeiro de
        # cada uma: uma corrente de Eventos a cada 10 min não vira uma Execução de dias.
        rest: dict[str, list[EventRef]] = defaultdict(list)
        for event in loose:
            if event.business_reference is not None and event.id not in how:
                rest[event.business_reference].append(event)
        for bucket in rest.values():
            head: EventRef | None = None
            for event in bucket:
                if (
                    head is None
                    or event.timestamp - head.timestamp > window
                    or not self.settings.compatible(head.operation, event.operation)
                ):
                    head = event
                    continue
                sets.union(event.id, head.id)
                how[event.id] = how[head.id] = "business_reference"

    def _by_proximity(
        self,
        events: list[EventRef],
        loose: list[EventRef],
        sets: _Sets,
        how: dict[str, Strategy | None],
        weak: set[str],
    ) -> None:
        proximity = self.settings.proximity

        def near(first: EventRef, second: EventRef) -> bool:
            return (
                first.attempt is not None
                and second.attempt is not None
                and abs(first.attempt - second.attempt) == 1
                and _gap(first, second) <= proximity
            )

        def by_resource(found: Iterable[EventRef]) -> dict[str, list[EventRef]]:
            buckets: dict[str, list[EventRef]] = defaultdict(list)
            for event in found:
                if event.resource is not None and event.attempt is not None:
                    buckets[event.resource].append(event)
            return buckets

        # Grupo dos soltos entre si, depois o grupo inteiro vai para o vizinho mais próximo.
        local = _Sets()
        for event in loose:
            local.find(event.id)
        for bucket in by_resource(loose).values():
            for event, other in _pairs(bucket, proximity):
                if near(event, other):
                    local.union(event.id, other.id)
        clusters: dict[str, list[EventRef]] = defaultdict(list)
        for event in loose:
            clusters[local.find(event.id)].append(event)
        settled = by_resource(event for event in events if event.anchored or event.id in how)
        for cluster in clusters.values():
            candidates = [
                (_gap(event, other), sets.find(other.id))
                for event in cluster
                if event.resource is not None
                for other in settled[event.resource]
                if near(event, other)
            ]
            if len(cluster) == 1 and not candidates:
                continue
            for event in cluster:
                if candidates:
                    sets.union(event.id, min(candidates)[1])
                else:
                    sets.union(event.id, cluster[0].id)
                how[event.id] = "temporal_proximity"
                weak.add(event.id)

    def _group(
        self, events: list[EventRef], how: Mapping[str, Strategy | None], weak: set[str]
    ) -> Group:
        events = sorted(events, key=_order)
        keys = {
            "execution_id": sorted({e.execution_id for e in events if e.execution_id}),
            "trace_id": sorted({e.trace_id for e in events if e.trace_id}),
            "cross_system": sorted({key for e in events for key in e.cross_keys}),
            "business_reference": sorted(
                {e.business_reference for e in events if e.business_reference}
            ),
        }
        if keys["execution_id"]:
            key = f"execution_id:{keys['execution_id'][0]}"
        elif keys["trace_id"]:
            key = f"trace_id:{keys['trace_id'][0]}"
        else:
            key = f"event:{events[0].id}"
        return Group(
            key=key,
            tenant_id=events[0].tenant_id,
            integration_id=events[0].integration_id,
            event_ids=tuple(e.id for e in events),
            severities=tuple(e.severity for e in events),
            first_event_at=events[0].timestamp,
            last_event_at=events[-1].timestamp,
            correlated_by={e.id: how.get(e.id) for e in events},
            keys=keys,
            # Fraca: proximidade temporal, ou Evento que nenhuma estratégia associou.
            low_confidence=any(e.id in weak for e in events)
            or not any(e.id in how for e in events),
        )


def _order(event: EventRef) -> tuple[datetime, str]:
    return event.order


def final_status(*, failed: bool, low_confidence: bool, closed: bool) -> Status:
    """Erro em qualquer Evento falha a Execução; sem erro, ela é confirmada só ao fechar, e a
    agrupada só por estratégia fraca fecha como `unknown`. O fechamento usa a mesma regra."""
    if failed:
        return "failed"
    if not closed:
        return "pending_confirmation"
    return "unknown" if low_confidence else "success"


def execution_status(group: Group, closed: bool) -> Status:
    return final_status(
        failed=any(severity in FAILED for severity in group.severities),
        low_confidence=group.low_confidence,
        closed=closed,
    )


def merge_plan(first_events: Mapping[str, datetime]) -> tuple[str | None, list[str]]:
    """Quando um grupo junta Execuções que já existiam: fica a de primeiro Evento mais antigo
    (desempate pelo id), e as outras são fundidas nela. Recebe {id: first_event_at}."""
    if not first_events:
        return None, []
    ordered = sorted(first_events, key=lambda target: (first_events[target], target))
    return ordered[0], ordered[1:]
