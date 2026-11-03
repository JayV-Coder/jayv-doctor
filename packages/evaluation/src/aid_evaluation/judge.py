"""Juiz LLM da Causa provável: a Causa do Diagnóstico diz o mesmo que o gabarito? Os dois textos
vão como dados não confiáveis, delimitados pelo GuardedLLM. Uma amostra de 20% é conferida por
uma pessoa (comando `sample`)."""

from aid_diagnosis_engine.llm.client import GuardedLLM
from aid_diagnosis_engine.llm.guards import Untrusted
from pydantic import BaseModel, ConfigDict, Field

SYSTEM = (
    "Você avalia diagnósticos de falhas de integração. Compare a causa esperada (gabarito de um"
    " especialista) com a causa proposta e responda se descrevem a mesma causa raiz, mesmo com"
    " palavras diferentes. Detalhe a mais não invalida; causa diferente ou vaga demais invalida."
)


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    same_cause: bool
    reason: str = Field(max_length=300)


class LLMJudge:
    def __init__(self, llm: GuardedLLM) -> None:
        self.llm = llm

    async def __call__(self, expected: str, proposed: str) -> bool:
        result = await self.llm.structured(
            scope="avaliacao-juiz",
            system=SYSTEM,
            instructions="Responda no schema: a causa proposta é a mesma causa raiz do gabarito?",
            untrusted=[
                Untrusted("expected_cause", "gabarito", expected),
                Untrusted("proposed_cause", "proposta", proposed),
            ],
            schema=Verdict,
            tier="fast",
            max_tokens=300,
        )
        return result.output.same_cause
