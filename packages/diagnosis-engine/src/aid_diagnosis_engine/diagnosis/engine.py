"""Orquestração das 6 etapas: 1 validação e classificação, 2 correlação, 3 Regras, 4 Base de
conhecimento, 5 LLM e 6 verificação. O modo `rules_only` pula as etapas 4 e 5; a Cota de IA
esgotada e a falha do LLM caem nele também, com a nota e, na falha, o status `failed_llm`."""

from collections.abc import Awaitable, Callable, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from aid_diagnosis_engine.diagnosis.enrichment import apply_enrichment
from aid_diagnosis_engine.diagnosis.model import (
    DiagnosisDraft,
    EventItem,
    IncidentInfo,
    Loader,
    Mode,
    RuleItem,
    Stage,
)
from aid_diagnosis_engine.diagnosis.prompt import SYSTEM, instructions, knowledge_query, untrusted
from aid_diagnosis_engine.diagnosis.rules_only import rules_draft
from aid_diagnosis_engine.diagnosis.schema import LLMDiagnosis
from aid_diagnosis_engine.diagnosis.verify import verify
from aid_diagnosis_engine.llm.base import LLMError, Tier, Usage
from aid_diagnosis_engine.llm.client import GuardedLLM

OnStage = Callable[[Stage], Awaitable[None]]
MAX_TOKENS = 4096


class DiagnosisError(Exception):
    """O Diagnóstico não pode rodar (Incidente sumiu): status `failed`."""


async def _nothing(stage: Stage) -> None:
    return None


# Roteamento por complexidade (#47): `fixed` usa sempre o modelo maior (o padrão até a avaliação
# decidir), `fast` sempre o menor, `by_complexity` o menor quando as Regras já explicam o caso, e
# `classify_first` pede a classificação ao menor e só manda a interpretação ao maior quando a
# confiança dele é baixa ou ele discorda das Regras.
Routing = Literal["fixed", "fast", "by_complexity", "classify_first"]
SIMPLE_EVENTS = 30
CLASSIFY_TOKENS = 200
CLASSIFIER_CONFIDENCE = 0.7


class Classification(BaseModel):
    """O que o modelo menor responde no `classify_first`: a categoria e a confiança heurística."""

    classification: str = Field(max_length=60)
    confidence: float = Field(ge=0, le=1)


def choose_tier(
    routing: Routing,
    incident: IncidentInfo,
    events: Sequence[EventItem],
    rules: Sequence[RuleItem],
) -> Tier:
    """Caso simples: as Regras que dispararam têm uma categoria só, conhecida e igual à do
    Incidente, com poucos Eventos. O resto (sem Regra, categorias em conflito entre as Regras ou
    com o Incidente, muito Evento) vai ao maior. `classify_first` decide depois da classificação
    do menor (`after_classification`)."""
    if routing in ("fixed", "classify_first"):
        return "reasoning"
    if routing == "fast":
        return "fast"
    categories = {rule.category for rule in rules}
    simple = (
        categories == {incident.category}
        and incident.category not in (None, "UNKNOWN")
        and len(events) <= SIMPLE_EVENTS
    )
    return "fast" if simple else "reasoning"


def after_classification(found: Classification, incident: IncidentInfo) -> Tier:
    """O menor concordou com a categoria do Incidente, com confiança: ele mesmo interpreta."""
    agreed = found.classification.strip().upper() == (incident.category or "").upper()
    return "fast" if agreed and found.confidence >= CLASSIFIER_CONFIDENCE else "reasoning"


class DiagnosisEngine:
    def __init__(
        self,
        llm: GuardedLLM | None,
        *,
        scope: str,
        without_ai: str = "Cota de IA indisponível: Diagnóstico só com as Regras.",
        routing: Routing = "fixed",
    ) -> None:
        """`llm` ausente = sem IA (modo rules_only, sem Cota ou envio desligado), e `without_ai`
        diz por quê; `scope` é a Organização; `routing` escolhe o modelo do caso (#47)."""
        self.llm = llm
        self.scope = scope
        self.without_ai = without_ai
        self.routing = routing
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
        tier = choose_tier(self.routing, incident, events, rules)
        if self.routing == "classify_first":
            try:
                found = await self.llm.structured(
                    scope=self.scope,
                    system=SYSTEM,
                    instructions="Classifique a falha (categoria) e dê a confiança de 0 a 1.",
                    untrusted=untrusted(rules, events, knowledge, enrichment),
                    schema=Classification,
                    tier="fast",
                    max_tokens=CLASSIFY_TOKENS,
                )
                tier = after_classification(found.output, incident)
            except LLMError:
                tier = "reasoning"
        try:
            result = await self.llm.structured(
                scope=self.scope,
                system=SYSTEM,
                instructions=instructions(incident),
                untrusted=untrusted(rules, events, knowledge, enrichment),
                schema=LLMDiagnosis,
                tier=tier,
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
