"""Diagnósticos dentro de `tenant_tx`: leitura pelo RLS, pedido e configuração pelas funções do
banco, que conferem o Papel na tabela."""

from typing import Any

from sqlalchemy import text

from aid_api.core.auth import Claims
from aid_api.core.db import translated_tx
from aid_api.core.errors import ApiError
from aid_api.diagnoses.schemas import (
    DiagnosisDetail,
    DiagnosisQueued,
    DiagnosisRequest,
    DiagnosisSettings,
    DiagnosisSummary,
    Evidence,
    Hypothesis,
    Recommendation,
)

SUMMARY = (
    "id::text, incident_id::text, version, status, stage, requested_mode, mode, classification,"
    " confidence::float, requires_human_review, created_at, published_at"
)


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Diagnóstico não encontrado.")


ERRORS = {
    "P0002": lambda: ApiError(404, "not_found", "Incidente não encontrado."),
    "42501": lambda: ApiError(403, "forbidden", "Seu Papel não permite esta ação."),
    "23505": lambda: ApiError(
        409, "idempotency_conflict", "Chave de idempotência já usada em outro Incidente."
    ),
}


class DiagnosisRepository:
    async def request(
        self, claims: Claims, incident: str, body: DiagnosisRequest, key: str
    ) -> DiagnosisQueued:
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                await connection.execute(
                    text(
                        "select id::text, status, version"
                        " from doctor.request_diagnosis(cast(:i as uuid), :m, :kb, :k)"
                    ),
                    {"i": incident, "m": body.mode, "kb": body.include_knowledge_base, "k": key},
                )
            ).one()
        return DiagnosisQueued(diagnosis_id=row.id, status=row.status, version=row.version)

    async def for_incident(self, claims: Claims, incident: str) -> list[DiagnosisSummary]:
        async with translated_tx(claims, ERRORS) as connection:
            exists = await connection.scalar(
                text("select 1 from doctor.incidents where id = cast(:i as uuid)"), {"i": incident}
            )
            if exists is None:
                raise ApiError(404, "not_found", "Incidente não encontrado.")
            result = await connection.execute(
                text(
                    f"select {SUMMARY} from doctor.diagnoses"  # noqa: S608
                    " where incident_id = cast(:i as uuid) order by version desc"
                ),
                {"i": incident},
            )
            return [DiagnosisSummary.model_validate(dict(row)) for row in result.mappings()]

    async def detail(self, claims: Claims, target: str) -> DiagnosisDetail:
        async with translated_tx(claims, ERRORS) as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            f"select {SUMMARY}, probable_cause, responsible_system,"  # noqa: S608
                            " include_knowledge_base, verification_notes, provider, model,"
                            " ruleset_version, input_tokens, output_tokens, duration_ms, error"
                            " from doctor.diagnoses where id = cast(:d as uuid)"
                        ),
                        {"d": target},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise not_found()
            params = {"d": target}
            hypotheses = await connection.execute(
                text(
                    "select rank, statement, confidence::float from doctor.diagnosis_hypotheses"
                    " where diagnosis_id = cast(:d as uuid) order by rank"
                ),
                params,
            )
            evidence = await connection.execute(
                text(
                    # Da Regra, o primeiro Evento que ela apontou, com o instante: o link leva a
                    # consulta do Evento direto à partição dele.
                    "select e.rank, e.kind, coalesce(e.event_id, e.raw_log_object_id, e.chunk_id,"
                    " e.global_chunk_id, e.rule_match_id)::text as ref_id,"
                    " coalesce(e.event_timestamp, me.timestamp) as event_timestamp,"
                    " e.label, e.finding,"
                    " coalesce(e.event_id, m.matched_event_ids[1])::text as event_id,"
                    " coalesce(ev.execution_ref, m.execution_id)::text as execution_id"
                    " from doctor.diagnosis_evidence e"
                    " left join doctor.rule_matches m"
                    " on m.tenant_id = e.tenant_id and m.id = e.rule_match_id"
                    " left join doctor.executions x"
                    " on x.tenant_id = m.tenant_id and x.id = m.execution_id"
                    " left join doctor.events me on me.tenant_id = m.tenant_id"
                    " and me.id = m.matched_event_ids[1]"
                    " and me.timestamp between x.first_event_at and x.last_event_at"
                    " left join doctor.events ev on ev.tenant_id = e.tenant_id"
                    " and ev.id = e.event_id and ev.timestamp = e.event_timestamp"
                    " where e.diagnosis_id = cast(:d as uuid) order by e.rank"
                ),
                params,
            )
            recommendations = await connection.execute(
                text(
                    "select rank, text, kind from doctor.diagnosis_recommendations"
                    " where diagnosis_id = cast(:d as uuid) order by rank"
                ),
                params,
            )
            data: dict[str, Any] = dict(row)
            return DiagnosisDetail.model_validate(
                {
                    **data,
                    "hypotheses": [
                        Hypothesis.model_validate(dict(h)) for h in hypotheses.mappings()
                    ],
                    "evidence": [Evidence.model_validate(dict(e)) for e in evidence.mappings()],
                    "recommendations": [
                        Recommendation.model_validate(dict(r)) for r in recommendations.mappings()
                    ],
                }
            )

    async def settings(self, claims: Claims) -> DiagnosisSettings:
        async with translated_tx(claims, ERRORS) as connection:
            enabled = await connection.scalar(
                text(
                    "select auto_diagnose_critical from doctor.tenants"
                    " where id = (select doctor.current_tenant_id())"
                )
            )
        return DiagnosisSettings(auto_diagnose_critical=bool(enabled))

    async def update_settings(self, claims: Claims, new: DiagnosisSettings) -> DiagnosisSettings:
        async with translated_tx(claims, ERRORS) as connection:
            await connection.execute(
                text("select doctor.set_auto_diagnosis(:e)"), {"e": new.auto_diagnose_critical}
            )
        return new


def get_diagnosis_repository() -> DiagnosisRepository:
    return DiagnosisRepository()
