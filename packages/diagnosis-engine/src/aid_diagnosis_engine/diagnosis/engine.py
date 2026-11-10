"""Orquestração das 6 etapas: 1 validação e classificação, 2 correlação, 3 Regras, 4 Base de
conhecimento, 5 LLM e 6 verificação. O modo `rules_only` pula as etapas 4 e 5; a Cota de IA
esgotada e a falha do LLM caem nele também, com a nota e, na falha, o status `failed_llm`."""

from collections.abc import Awaitable, Callable

from aid_diagnosis_engine.diagnosis.enrichment import apply_enrichment
from aid_diagnosis_engine.diagnosis.model import DiagnosisDraft, Loader, Mode, Stage
from aid_diagnosis_engine.diagnosis.prompt import SYSTEM, instructions, knowledge_query, untrusted
from aid_diagnosis_engine.diagnosis.rules_only import rules_draft
from aid_diagnosis_engine.diagnosis.schema import LLMDiagnosis
from aid_diagnosis_engine.diagnosis.verify import verify
from aid_diagnosis_engine.llm.base import LLMError, Usage
from aid_diagnosis_engine.llm.client import GuardedLLM

OnStage = Callable[[Stage], Awaitable[None]]
MAX_TOKENS = 4096


class DiagnosisError(Exception):
    """O Diagnóstico não pode rodar (Incidente sumiu): status `failed`."""


async def _nothing(stage: Stage) -> None:
    return None


class DiagnosisEngine:
    def __init__(
        self,
        llm: GuardedLLM | None,
        *,
        scope: str,
        without_ai: str = "Cota de IA indisponível: Diagnóstico só com as Regras.",
    ) -> None:
        """`llm` ausente = sem IA (modo rules_only, sem Cota ou envio desligado), e `without_ai`
        diz por quê; `scope` é a Organização."""
        self.llm = llm
        self.scope = scope
        self.without_ai = without_ai
        self.usage: list[Usage] = []
        if llm is not None:
            llm.usage_sink = self._record

    async def _record(self, usage: Usage) -> None:
        self.usage.append(usage)

    async def run(
        self,
        loader: Loader,
        *,
        mode: Mode,
        include_knowledge_base: bool = True,
        on_stage: OnStage = _nothing,
    ) -> DiagnosisDraft:
        await on_stage("validation")
        incident = await loader.incident()
        if incident is None:
            raise DiagnosisError("Incidente não encontrado.")

        await on_stage("correlation")
        events = list(await loader.correlation())
        # Consulta de leitura no destino (#40): `EnrichmentPending` sobe e o worker devolve o
        # Diagnóstico à fila até o worker de Conectores responder.
        enrichment = list(await loader.enrichment())

        await on_stage("rules")
        rules = list(await loader.rules())
        notes: list[str] = []
        if not events:
            notes.append("Incidente sem Eventos carregados: Evidências insuficientes.")

        if mode == "hybrid" and self.llm is None:
            notes.append(self.without_ai)
            mode = "rules_only"
        if mode == "rules_only":
            await on_stage("verification")
            draft = rules_draft(incident, events, rules, mode="rules_only")
            draft.verification_notes[:0] = notes
            return apply_enrichment(draft, enrichment, incident)

        knowledge = []
        if include_knowledge_base:
            await on_stage("knowledge")
            try:
                knowledge = list(await loader.knowledge(knowledge_query(incident, events)))
            except LLMError:
                notes.append("Base de conhecimento indisponível: Diagnóstico sem ela.")

        await on_stage("llm")
        assert self.llm is not None  # noqa: S101 - garantido pelo modo acima
        try:
            result = await self.llm.structured(
                scope=self.scope,
                system=SYSTEM,
                instructions=instructions(incident),
                untrusted=untrusted(rules, events, knowledge, enrichment),
                schema=LLMDiagnosis,
                tier="reasoning",
                max_tokens=MAX_TOKENS,
            )
        except LLMError:
            await on_stage("verification")
            draft = rules_draft(incident, events, rules, mode="rules_only", status="failed_llm")
            draft.verification_notes[:0] = [
                *notes,
                "O modelo de IA falhou: Diagnóstico só com as Regras.",
            ]
            return self._with_usage(apply_enrichment(draft, enrichment, incident))

        await on_stage("verification")
        draft = verify(result.output, incident, events, rules, knowledge, enrichment)
        draft.verification_notes[:0] = notes
        return self._with_usage(apply_enrichment(draft, enrichment, incident))

    def _with_usage(self, draft: DiagnosisDraft) -> DiagnosisDraft:
        billed = [usage for usage in self.usage if not usage.cached]
        if billed:
            draft.provider = billed[-1].provider
            draft.model = billed[-1].model
        draft.input_tokens = sum(usage.input_tokens for usage in billed)
        draft.output_tokens = sum(usage.output_tokens for usage in billed)
        return draft
