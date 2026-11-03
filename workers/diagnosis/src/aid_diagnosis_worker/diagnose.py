"""Worker do Diagnóstico (`diagnosis.requested`, ticket #24). A mensagem leva só o id; quem a
recebe toma posse do Diagnóstico (`queued` → `running`), e entregas repetidas não fazem um
segundo. O contexto é lido com a claim do tenant do Incidente (RLS, como na API): nada de outra
Organização entra no prompt nem vira Evidência. A publicação grava tudo numa transação só."""

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import timedelta
from typing import Any, cast

from aid_db import platform_role, tenant_role
from aid_diagnosis_engine.diagnosis import (
    DiagnosisDraft,
    DiagnosisEngine,
    DiagnosisError,
    EventItem,
    IncidentInfo,
    KnowledgeItem,
    RuleItem,
    Stage,
)
from aid_diagnosis_engine.diagnosis.model import Mode
from aid_diagnosis_engine.llm.base import LLMError, LLMProvider
from aid_diagnosis_engine.llm.client import GuardedLLM
from aid_diagnosis_engine.rules.base import EventView
from aid_diagnosis_engine.rules.catalog import RULES, RULESET_VERSION
from aid_knowledge.store import search
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
DESCRIPTIONS = {rule.code: (rule.category, rule.description_pt) for rule in RULES}

ProviderFor = Callable[[str], LLMProvider]


async def ai_allowed(engine: AsyncEngine, tenant: str) -> bool:
    """Cota de IA da Organização. O controle de consumo chega com o #31 (`usage_records`); até
    lá, a IA está liberada para todas."""
    return True


class DbLoader:
    def __init__(
        self, engine: AsyncEngine, tenant: str, incident: str, provider: LLMProvider
    ) -> None:
        self.engine, self.tenant, self.incident_id, self.provider = (
            engine,
            tenant,
            incident,
            provider,
        )
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
        # Sem embedding (provedor fora), a busca segue só pelo texto, como na API.
        vector: list[float] | None
        try:
            [vector] = await self.provider.embed([query], input_type="query")
        except LLMError:
            vector = None
        async with self.engine.begin() as connection:
            await tenant_role(connection, self.tenant)
            hits = await search(
                connection,
                self.tenant,
                query,
                embedding=vector,
                model=self.provider.embedding_model if vector is not None else None,
                k=KNOWLEDGE_K,
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
                    " d.requested_mode, d.include_knowledge_base, d.attempts, t.llm_provider"
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
                    " label, finding) values (cast(:t as uuid), cast(:d as uuid), :r, :k,"
                    " cast(:event_id as uuid), :ts, cast(:chunk_id as uuid),"
                    " cast(:global_chunk_id as uuid), cast(:rule_match_id as uuid), :label,"
                    " :finding)"
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
        provider = provider_for(diagnosis.llm_provider)
        hybrid = diagnosis.requested_mode == "hybrid"
        allowed = hybrid and await ai_allowed(engine, diagnosis.tenant_id)
        motor = DiagnosisEngine(
            GuardedLLM(provider) if allowed else None, scope=diagnosis.tenant_id
        )
        loader = DbLoader(engine, diagnosis.tenant_id, diagnosis.incident_id, provider)
        draft = await motor.run(
            loader,
            mode=cast("Mode", diagnosis.requested_mode),
            include_knowledge_base=diagnosis.include_knowledge_base,
            on_stage=on_stage,
        )
        published = await publish(engine, diagnosis, draft)
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
