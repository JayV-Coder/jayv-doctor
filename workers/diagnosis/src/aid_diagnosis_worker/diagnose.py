"""Worker do Diagnóstico (`diagnosis.requested`, ticket #24). A mensagem leva só o id; quem a
recebe toma posse do Diagnóstico (`queued` → `running`), e entregas repetidas não fazem um
segundo. O contexto é lido com a claim do tenant do Incidente (RLS, como na API): nada de outra
Organização entra no prompt nem vira Evidência. A publicação grava tudo numa transação só."""

import json
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import timedelta
from typing import Any, cast

from aid_db import platform_role, tenant_role
from aid_diagnosis_engine.diagnosis import (
    DiagnosisDraft,
    DiagnosisEngine,
    DiagnosisError,
    EnrichmentItem,
    EnrichmentPending,
    EventItem,
    IncidentInfo,
    KnowledgeItem,
    RuleItem,
    Stage,
)
from aid_diagnosis_engine.diagnosis.model import Mode
from aid_diagnosis_engine.llm.base import LLMProvider, LLMUnavailableError
from aid_diagnosis_engine.llm.client import GuardedLLM
from aid_diagnosis_engine.rules.base import EventView
from aid_diagnosis_engine.rules.catalog import RULES, RULESET_VERSION
from aid_knowledge.store import previous_models, search
from aid_knowledge.vectors import query_vectors
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# Posse de um Diagnóstico em andamento: passado isso sem publicar, outra entrega pode retomá-lo.
LEASE = timedelta(minutes=5)
# Na terceira falha que não seja do LLM (banco, dado, código), o Diagnóstico vira `failed` em vez
# de voltar à fila até a DLQ.
MAX_ATTEMPTS = 3
MAX_EVENTS = 200
MAX_RULES = 20
KNOWLEDGE_K = 5
# Consultas de enriquecimento por Diagnóstico (#40) e quanto se espera pelo worker de Conectores.
MAX_LOOKUPS = 5
LOOKUP_WAIT = timedelta(minutes=5)
# Sistema consultado, pelo provedor do Conector do Mapa.
LOOKUP_SYSTEMS = {"salesforce": "salesforce", "odata": "sap"}
DESCRIPTIONS = {rule.code: (rule.category, rule.description_pt) for rule in RULES}

# (llm_provider, ai_project) → provedor; o projeto só vale para o dedicado (ADR-0018).
ProviderFor = Callable[[str, str | None], LLMProvider]


log = logging.getLogger(__name__)
LLM_DISABLED = (
    "Envio de evidências ao LLM desligado pela Organização: Diagnóstico só com as Regras."
)
QUOTA_EXHAUSTED = "Cota de IA do mês esgotada: Diagnóstico só com as Regras."


async def llm_enabled(engine: AsyncEngine, tenant: str) -> bool:
    """A Organização permite enviar evidências ao LLM (#29)?"""
    async with engine.begin() as connection:
        await platform_role(connection)
        enabled = await connection.scalar(
            text("select llm_enabled from doctor.tenants where id = cast(:t as uuid)"),
            {"t": tenant},
        )
    return bool(enabled)


async def reserve_llm(engine: AsyncEngine, diagnosis: Any, provider: str) -> bool:
    """Reserva uma unidade da Cota de IA (#31) antes de chamar o LLM, de forma atômica no banco:
    Diagnósticos em paralelo não passam do limite, e a mesma entrega não reserva duas vezes."""
    async with engine.begin() as connection:
        await platform_role(connection)
        reserved = await connection.scalar(
            text("select doctor.reserve_llm_quota(cast(:t as uuid), cast(:d as uuid), :p)"),
            {"t": diagnosis.tenant_id, "d": diagnosis.id, "p": provider},
        )
    return bool(reserved)


def load_prices(raw: str | None) -> dict[str, tuple[float, float]]:
    """`AID_LLM_PRICES` (JSON por modelo, `input_per_mtok`/`output_per_mtok`), da tabela oficial
    do provedor. Lida uma vez; entrada inválida é ignorada, e o custo daquele modelo fica em
    aberto, sem atrapalhar o Diagnóstico."""
    if not raw:
        return {}
    try:
        table = json.loads(raw)
    except ValueError:
        log.warning("AID_LLM_PRICES não é JSON válido: custo estimado desligado")
        return {}
    prices: dict[str, tuple[float, float]] = {}
    for model, price in table.items() if isinstance(table, dict) else []:
        try:
            prices[str(model)] = (float(price["input_per_mtok"]), float(price["output_per_mtok"]))
        except (KeyError, TypeError, ValueError):
            log.warning("AID_LLM_PRICES: preço inválido para %s", model)
    return prices


PRICES = load_prices(os.environ.get("AID_LLM_PRICES"))


def estimate_cost(model: str | None, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES.get(model or "")
    if price is None:
        return None
    return round(input_tokens / 1e6 * price[0] + output_tokens / 1e6 * price[1], 6)


def no_others(name: str) -> LLMProvider:
    raise LLMUnavailableError(f"sem provedor para o índice de {name}")


class DbLoader:
    def __init__(
        self,
        engine: AsyncEngine,
        tenant: str,
        incident: str,
        provider: LLMProvider | None,
        diagnosis: str = "",
        profile: str = "standard",
        others: Callable[[str], LLMProvider] | None = None,
    ) -> None:
        self.engine, self.tenant, self.incident_id, self.provider = (
            engine,
            tenant,
            incident,
            provider,
        )
        self.diagnosis_id = diagnosis
        # Perfil de IA e os provedores dos índices antigos (reindex em andamento, ADR-0018).
        self.profile = profile
        self.others = others
        self.rule_code: str | None = None

    async def _rows(self, sql: str, **params: Any) -> Sequence[Any]:
        async with self.engine.begin() as connection:
            await tenant_role(connection, self.tenant)
            return (await connection.execute(text(sql), {"i": self.incident_id, **params})).all()

    async def incident(self) -> IncidentInfo | None:
        rows = await self._rows(
            "select i.id::text, i.number, i.title, i.category, i.severity, i.rule_code, g.name,"
            " g.source_system, g.target_system from doctor.incidents i"
            " join doctor.integrations g on g.tenant_id = i.tenant_id and g.id = i.integration_id"
            " where i.id = cast(:i as uuid)"
        )
        if not rows:
            return None
        row = rows[0]
        self.rule_code = row.rule_code
        return IncidentInfo(
            id=row.id,
            number=row.number,
            title=row.title,
            category=row.category,
            severity=row.severity,
            integration_name=row.name,
            source_system=row.source_system,
            target_system=row.target_system,
        )

    async def correlation(self) -> Sequence[EventItem]:
        # Erros e avisos primeiro, até o limite; depois em ordem cronológica.
        rows = await self._rows(
            "select e.id::text, e.timestamp, e.severity, e.operation, e.error, e.attributes,"
            " x.id::text as execution_id from doctor.incident_executions ie"
            " join doctor.executions x on x.tenant_id = ie.tenant_id and x.id = ie.execution_id"
            " join doctor.events e on e.tenant_id = x.tenant_id and e.execution_ref = x.id"
            " and e.timestamp between x.first_event_at and x.last_event_at"
            " where ie.incident_id = cast(:i as uuid)"
            " order by (e.severity in ('WARNING', 'ERROR', 'CRITICAL')) desc, e.timestamp desc"
            " limit :n",
            n=MAX_EVENTS,
        )
        items = [
            EventItem(
                EventView(
                    id=row.id,
                    timestamp=row.timestamp,
                    severity=row.severity,
                    operation=row.operation,
                    error=row.error,
                    attributes=row.attributes or {},
                ),
                row.execution_id,
            )
            for row in rows
        ]
        return sorted(items, key=lambda item: item.view.timestamp)

    async def enrichment(self) -> Sequence[EnrichmentItem]:
        """Etapa 2 (#40): as consultas de leitura deste Diagnóstico. Na primeira passagem, pede
        as que os Mapas com `lookup` indicam e devolve o Diagnóstico à fila; com todas
        respondidas, entrega o resultado. Pendentes há mais de 5 min são expiradas pela rota
        `/enrichment/expire`."""
        rows = await self._rows(
            "select id::text, system, entity, field, reference, outcome, record_id,"
            " record_status, checked_at from doctor.enrichments"
            " where diagnosis_id = cast(:d as uuid) order by created_at, reference",
            d=self.diagnosis_id,
        )
        if any(row.outcome == "pending" for row in rows):
            raise EnrichmentPending
        if rows:
            return [
                EnrichmentItem(
                    id=row.id,
                    system=row.system,
                    entity=row.entity,
                    field=row.field,
                    reference=row.reference,
                    outcome=row.outcome,
                    record_id=row.record_id,
                    record_status=row.record_status,
                    checked_at=row.checked_at,
                )
                for row in rows
            ]
        wanted = await self._lookups()
        if not wanted:
            return []
        async with self.engine.begin() as connection:
            await platform_role(connection)
            await connection.execute(
                text(
                    "insert into doctor.enrichments (tenant_id, diagnosis_id, mapping_id,"
                    " connector_id, reference, system, entity, field) values (cast(:t as uuid),"
                    " cast(:d as uuid), cast(:m as uuid), cast(:c as uuid), :r, :s, :e, :f)"
                    " on conflict (tenant_id, diagnosis_id, mapping_id, reference) do nothing"
                ),
                [{"t": self.tenant, "d": self.diagnosis_id, **item} for item in wanted],
            )
            await connection.execute(
                text(
                    "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                    " values (cast(:t as uuid), 'enrichment.requested', cast(:p as jsonb))"
                ),
                {"t": self.tenant, "p": json.dumps({"diagnosis_id": self.diagnosis_id})},
            )
        raise EnrichmentPending

    async def _lookups(self) -> list[dict[str, Any]]:
        """Uma consulta por (Mapa com `lookup`, chave) das Execuções do Incidente, até 5."""
        rows = await self._rows(
            "select distinct m.id::text as mapping, m.lookup, c.provider, k.key"
            " from doctor.incident_executions ie"
            " join doctor.executions x on x.tenant_id = ie.tenant_id and x.id = ie.execution_id"
            " join doctor.events e on e.tenant_id = x.tenant_id and e.execution_ref = x.id"
            " and e.timestamp between x.first_event_at and x.last_event_at"
            " cross join lateral unnest(e.cross_keys) as k(key)"
            " join doctor.correlation_mappings m on m.tenant_id = e.tenant_id"
            " and m.integration_id = e.integration_id and m.lookup is not null"
            " and k.key like m.id::text || ':%'"
            " join doctor.connectors c on c.tenant_id = m.tenant_id"
            " and c.id = cast(m.lookup ->> 'connector_id' as uuid)"
            " where ie.incident_id = cast(:i as uuid) and e.cross_keys is not null"
            " order by m.id::text, k.key limit :n",
            n=MAX_LOOKUPS,
        )
        found = []
        for row in rows:
            lookup = dict(row.lookup)
            value = row.key.split(":", 1)[1]
            pad = int(lookup.get("pad_left") or 0)
            found.append(
                {
                    "m": row.mapping,
                    "c": lookup["connector_id"],
                    "r": value.rjust(pad, "0")[:256],
                    "s": LOOKUP_SYSTEMS.get(row.provider, row.provider),
                    "e": lookup["entity"],
                    "f": lookup["field"],
                }
            )
        return found

    async def rules(self) -> Sequence[RuleItem]:
        rows = await self._rows(
            "select m.id::text, m.rule_code, m.rule_version, m.execution_id::text,"
            " m.matched_event_ids::text[] as events from doctor.rule_matches m"
            " join doctor.incident_executions ie"
            " on ie.tenant_id = m.tenant_id and ie.execution_id = m.execution_id"
            " where ie.incident_id = cast(:i as uuid)"
            " order by (m.rule_code = :code) desc, m.created_at limit :n",
            code=self.rule_code or "",
            n=MAX_RULES,
        )
        return [
            RuleItem(
                id=row.id,
                rule_code=row.rule_code,
                rule_version=row.rule_version,
                category=DESCRIPTIONS.get(row.rule_code, ("UNKNOWN", ""))[0],
                description=DESCRIPTIONS.get(row.rule_code, ("", row.rule_code))[1],
                execution_id=row.execution_id,
                matched_event_ids=tuple(row.events),
            )
            for row in rows
        ]

    async def knowledge(self, query: str) -> Sequence[KnowledgeItem]:
        # Embedding fora da transação; a busca, com a claim do tenant (o RAG não cruza tenants).
        # Sem embedding (provedor fora), a busca segue só pelo texto, como na API. Perfil de IA
        # trocado: os índices antigos que o perfil permite entram até o reindex terminar.
        models: list[str] = []
        # Sem provedor (envio ao LLM desligado), nada de embedding: nem a consulta aos índices.
        if self.provider is not None and self.others is not None:
            async with self.engine.begin() as connection:
                await tenant_role(connection, self.tenant)
                models = await previous_models(connection, self.tenant, None)
        vectors = await query_vectors(
            query, self.provider, self.profile, models, self.others or no_others
        )
        async with self.engine.begin() as connection:
            await tenant_role(connection, self.tenant)
            hits = await search(
                connection,
                self.tenant,
                query,
                embedding=vectors.embedding,
                model=vectors.model,
                k=KNOWLEDGE_K,
                previous=vectors.previous,
            )
        return [
            KnowledgeItem(hit.chunk_id, hit.origin, hit.title, hit.heading, hit.content)
            for hit in hits
        ]


async def claim(engine: AsyncEngine, diagnosis_id: str) -> Any:
    async with engine.begin() as connection:
        await platform_role(connection)
        return (
            await connection.execute(
                text(
                    "update doctor.diagnoses d set status = 'running', stage = 'validation',"
                    " started_at = now(), attempts = d.attempts + 1"
                    " from doctor.tenants t where t.id = d.tenant_id and d.id = cast(:d as uuid)"
                    " and (d.status = 'queued' or d.status = 'running'"
                    " and d.started_at < now() - make_interval(secs => :lease))"
                    " returning d.id::text, d.tenant_id::text, d.incident_id::text,"
                    " d.requested_mode, d.include_knowledge_base, d.attempts, t.llm_provider,"
                    " t.ai_project, t.ai_profile"
                ),
                {"d": diagnosis_id, "lease": LEASE.total_seconds()},
            )
        ).first()


async def set_stage(engine: AsyncEngine, diagnosis_id: str, stage: Stage) -> None:
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "update doctor.diagnoses set stage = :s"
                " where id = cast(:d as uuid) and status = 'running'"
            ),
            {"d": diagnosis_id, "s": stage},
        )


async def release(engine: AsyncEngine, diagnosis: Any) -> None:
    """Devolve à fila sem esperar o prazo de posse: a próxima entrega retoma na hora."""
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "update doctor.diagnoses set status = 'queued', stage = 'queued', started_at = null"
                " where id = cast(:d as uuid) and status = 'running'"
            ),
            {"d": diagnosis.id},
        )


async def wait_enrichment(engine: AsyncEngine, diagnosis: Any) -> None:
    """Volta à fila na etapa 2 esperando as consultas, sem contar a passagem como tentativa: o
    worker de Conectores (ou a expiração) pede o Diagnóstico de novo."""
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "update doctor.diagnoses set status = 'queued', stage = 'correlation',"
                " started_at = null, attempts = greatest(attempts - 1, 0)"
                " where id = cast(:d as uuid) and status = 'running'"
            ),
            {"d": diagnosis.id},
        )


async def expire_enrichment(
    engine: AsyncEngine, wait: timedelta = LOOKUP_WAIT, idle: timedelta = timedelta(minutes=1)
) -> int:
    """Rota agendada `/enrichment/expire`, a cada 5 min. Consulta sem resposta em 5 min vira
    `failed` e o Diagnóstico segue sem ela. E o Diagnóstico que ficou na fila com todas as
    consultas respondidas (a resposta chegou antes de ele voltar à fila, ou o pedido de retomada
    se perdeu) é pedido de novo. Devolve quantos Diagnósticos foram retomados."""
    async with engine.begin() as connection:
        await platform_role(connection)
        expired = list(
            await connection.execute(
                text(
                    "update doctor.enrichments set outcome = 'failed', checked_at = now(),"
                    " error = 'O Conector não respondeu à consulta a tempo.'"
                    " where outcome = 'pending' and created_at < now() - make_interval(secs => :w)"
                    " returning tenant_id::text, diagnosis_id::text"
                ),
                {"w": wait.total_seconds()},
            )
        )
        stranded = list(
            await connection.execute(
                text(
                    "select d.tenant_id::text, d.id::text as diagnosis_id from doctor.diagnoses d"
                    " where d.status = 'queued' and d.stage = 'correlation'"
                    " and d.updated_at <= now() - make_interval(secs => :idle)"
                    " and exists (select 1 from doctor.enrichments n"
                    "  where n.tenant_id = d.tenant_id and n.diagnosis_id = d.id)"
                    " and not exists (select 1 from doctor.enrichments n"
                    "  where n.tenant_id = d.tenant_id and n.diagnosis_id = d.id"
                    "  and n.outcome = 'pending')"
                ),
                {"idle": idle.total_seconds()},
            )
        )
        resumed = sorted({(row[0], row[1]) for row in [*expired, *stranded]})
        if resumed:
            await connection.execute(
                text(
                    "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                    " values (cast(:t as uuid), 'diagnosis.requested', cast(:p as jsonb))"
                ),
                [
                    {"t": tenant, "p": json.dumps({"diagnosis_id": diagnosis})}
                    for tenant, diagnosis in resumed
                ],
            )
        return len(resumed)


async def fail(engine: AsyncEngine, diagnosis: Any, error: str) -> None:
    """Final como os outros: com `published_at`, duração e a mensagem `diagnosis.published`."""
    async with engine.begin() as connection:
        await platform_role(connection)
        updated = await connection.scalar(
            text(
                "update doctor.diagnoses set status = 'failed', stage = 'done', error = :e,"
                " published_at = now(),"
                " duration_ms = (extract(epoch from now() - created_at) * 1000)::int"
                " where id = cast(:d as uuid) and status = 'running' returning id"
            ),
            {"d": diagnosis.id, "e": error[:500]},
        )
        if updated is not None:
            await announce(connection, diagnosis, "failed")


async def announce(connection: Any, diagnosis: Any, status: str) -> None:
    await connection.execute(
        text(
            "insert into doctor.outbox_messages (tenant_id, topic, payload)"
            " values (cast(:t as uuid), 'diagnosis.published', cast(:p as jsonb))"
        ),
        {
            "t": diagnosis.tenant_id,
            "p": json.dumps(
                {
                    "diagnosis_id": diagnosis.id,
                    "incident_id": diagnosis.incident_id,
                    "status": status,
                }
            ),
        },
    )


def _evidence_row(diagnosis: Any, rank: int, item: Any) -> dict[str, Any]:
    columns = {
        "event": "event_id",
        "chunk": "chunk_id",
        "global_chunk": "global_chunk_id",
        "rule_match": "rule_match_id",
        "enrichment": "enrichment_id",
    }
    row: dict[str, Any] = {
        "t": diagnosis.tenant_id,
        "d": diagnosis.id,
        "r": rank,
        "k": item.kind,
        "event_id": None,
        "chunk_id": None,
        "global_chunk_id": None,
        "rule_match_id": None,
        "enrichment_id": None,
        "ts": item.event_timestamp,
        "label": item.label,
        "finding": item.finding,
    }
    row[columns[item.kind]] = item.ref_id
    return row


async def publish(engine: AsyncEngine, diagnosis: Any, draft: DiagnosisDraft) -> bool:
    async with engine.begin() as connection:
        await platform_role(connection)
        current = await connection.scalar(
            text("select status from doctor.diagnoses where id = cast(:d as uuid) for update"),
            {"d": diagnosis.id},
        )
        # Outra entrega retomou depois do prazo de posse e já publicou.
        if current != "running":
            return False
        base = {"t": diagnosis.tenant_id, "d": diagnosis.id}
        if draft.hypotheses:
            await connection.execute(
                text(
                    "insert into doctor.diagnosis_hypotheses (tenant_id, diagnosis_id, rank,"
                    " statement, confidence) values (cast(:t as uuid), cast(:d as uuid), :r,"
                    " :s, :c)"
                ),
                [
                    {**base, "r": rank, "s": item.statement, "c": item.confidence}
                    for rank, item in enumerate(draft.hypotheses, 1)
                ],
            )
        if draft.evidence:
            await connection.execute(
                text(
                    "insert into doctor.diagnosis_evidence (tenant_id, diagnosis_id, rank, kind,"
                    " event_id, event_timestamp, chunk_id, global_chunk_id, rule_match_id,"
                    " enrichment_id, label, finding) values (cast(:t as uuid), cast(:d as uuid),"
                    " :r, :k, cast(:event_id as uuid), :ts, cast(:chunk_id as uuid),"
                    " cast(:global_chunk_id as uuid), cast(:rule_match_id as uuid),"
                    " cast(:enrichment_id as uuid), :label, :finding)"
                ),
                [
                    _evidence_row(diagnosis, rank, item)
                    for rank, item in enumerate(draft.evidence, 1)
                ],
            )
        if draft.recommendations:
            await connection.execute(
                text(
                    "insert into doctor.diagnosis_recommendations (tenant_id, diagnosis_id, rank,"
                    " text, kind) values (cast(:t as uuid), cast(:d as uuid), :r, :x, :k)"
                ),
                [
                    {**base, "r": rank, "x": item.text, "k": item.kind}
                    for rank, item in enumerate(draft.recommendations, 1)
                ],
            )
        await connection.execute(
            text(
                "update doctor.diagnoses set status = :status, stage = 'done', mode = :mode,"
                " classification = :classification, probable_cause = :cause,"
                " confidence = :confidence, responsible_system = :system,"
                " requires_human_review = :review, verification_notes = cast(:notes as jsonb),"
                " provider = :provider, model = :model, ruleset_version = :ruleset,"
                " input_tokens = :input, output_tokens = :output, published_at = now(),"
                " duration_ms = (extract(epoch from now() - created_at) * 1000)::int"
                " where id = cast(:d as uuid)"
            ),
            {
                "d": diagnosis.id,
                "status": draft.status,
                "mode": draft.mode,
                "classification": draft.classification,
                "cause": draft.probable_cause,
                "confidence": draft.confidence,
                "system": draft.responsible_system,
                "review": draft.requires_human_review,
                "notes": json.dumps(draft.verification_notes, ensure_ascii=False),
                "provider": draft.provider,
                "model": draft.model,
                "ruleset": RULESET_VERSION,
                "input": draft.input_tokens,
                "output": draft.output_tokens,
            },
        )
        if draft.input_tokens or draft.output_tokens:
            # Tokens na mesma transação da publicação: o uso não se perde sem o Diagnóstico.
            await connection.execute(
                text(
                    "update doctor.usage_llm set provider = :p, model = :m, input_tokens = :i,"
                    " output_tokens = :o, cost_estimate = :c"
                    " where tenant_id = cast(:t as uuid) and diagnosis_id = cast(:d as uuid)"
                ),
                {
                    "t": diagnosis.tenant_id,
                    "d": diagnosis.id,
                    "p": draft.provider or "desconhecido",
                    "m": draft.model,
                    "i": draft.input_tokens,
                    "o": draft.output_tokens,
                    "c": estimate_cost(draft.model, draft.input_tokens, draft.output_tokens),
                },
            )
        await announce(connection, diagnosis, draft.status)
    return True


async def diagnose(
    engine: AsyncEngine, payload: Mapping[str, Any], provider_for: ProviderFor
) -> str:
    diagnosis = await claim(engine, str(payload["diagnosis_id"]))
    if diagnosis is None:
        return "ignored"

    async def on_stage(stage: Stage) -> None:
        await set_stage(engine, diagnosis.id, stage)

    # Tudo depois da posse fica aqui dentro: nenhuma falha deixa o Diagnóstico `running`.
    try:
        provider = provider_for(diagnosis.llm_provider, diagnosis.ai_project)
        hybrid = diagnosis.requested_mode == "hybrid"
        enabled = await llm_enabled(engine, diagnosis.tenant_id)
        allowed = hybrid and enabled and await reserve_llm(engine, diagnosis, provider.name)
        motor = DiagnosisEngine(
            GuardedLLM(provider) if allowed else None,
            scope=diagnosis.tenant_id,
            without_ai=LLM_DISABLED if not enabled else QUOTA_EXHAUSTED,
        )
        # Envio ao LLM desligado: a Base também não gera o embedding da pergunta (só o texto). No
        # rules_only com o envio ligado, o embedding da Base continua.
        loader = DbLoader(
            engine,
            diagnosis.tenant_id,
            diagnosis.incident_id,
            provider if enabled else None,
            diagnosis.id,
            profile=diagnosis.ai_profile,
            others=lambda name: provider_for(name, None),
        )
        draft = await motor.run(
            loader,
            mode=cast("Mode", diagnosis.requested_mode),
            include_knowledge_base=diagnosis.include_knowledge_base,
            on_stage=on_stage,
        )
        published = await publish(engine, diagnosis, draft)
    except EnrichmentPending:
        await wait_enrichment(engine, diagnosis)
        return "waiting"
    except DiagnosisError as exc:
        await fail(engine, diagnosis, str(exc))
        return "failed"
    except Exception:
        if diagnosis.attempts >= MAX_ATTEMPTS:
            await fail(engine, diagnosis, "Erro interno ao gerar o Diagnóstico.")
            return "failed"
        # Banco ou rede: devolve à fila e deixa o Pub/Sub reentregar.
        await release(engine, diagnosis)
        raise
    return draft.status if published else "ignored"


async def open_automatic(engine: AsyncEngine, payload: Mapping[str, Any]) -> str | None:
    """`incident.opened`: com o automático ligado e o Incidente crítico, pede um Diagnóstico
    híbrido. A chave é o próprio Incidente: reentregas não pedem outro."""
    async with engine.begin() as connection:
        await platform_role(connection)
        incident = (
            await connection.execute(
                text(
                    "select i.id::text, i.tenant_id::text from doctor.incidents i"
                    " join doctor.tenants t on t.id = i.tenant_id"
                    " where i.id = cast(:i as uuid) and i.severity = 'critical'"
                    " and t.auto_diagnose_critical for update of i"
                ),
                {"i": str(payload["incident_id"])},
            )
        ).first()
        if incident is None:
            return None
        created = await connection.scalar(
            text(
                "insert into doctor.diagnoses (tenant_id, incident_id, version, requested_mode,"
                " mode, processing_key) select cast(:t as uuid), cast(:i as uuid),"
                " coalesce(max(version), 0) + 1, 'hybrid', 'hybrid', :k from doctor.diagnoses"
                " where tenant_id = cast(:t as uuid) and incident_id = cast(:i as uuid)"
                " on conflict (tenant_id, processing_key) do nothing returning id::text"
            ),
            {"t": incident.tenant_id, "i": incident.id, "k": f"auto:{incident.id}"},
        )
        if created is None:
            return None
        await connection.execute(
            text(
                "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                " values (cast(:t as uuid), 'diagnosis.requested', cast(:p as jsonb))"
            ),
            {"t": incident.tenant_id, "p": json.dumps({"diagnosis_id": created})},
        )
        return str(created)
