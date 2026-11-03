"""Provedor determinístico para testes: devolve respostas roteirizadas, na ordem, e guarda cada
pedido. Uma resposta pode ser texto (validado pelo schema, como num provedor real) ou exceção."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from aid_diagnosis_engine.llm.base import InputType, Msg, StructuredResult, Tier, Usage
from aid_diagnosis_engine.llm.client import validate_output

DIMENSIONS = 8


@dataclass
class FakeProvider:
    responses: list[str | Exception] = field(default_factory=list)
    name: str = "fake"
    requests: list[dict[str, Any]] = field(default_factory=list)

    @property
    def embedding_dimensions(self) -> int:
        return DIMENSIONS

    async def complete_structured(
        self,
        *,
        system: str,
        messages: Sequence[Msg],
        schema: type[Any],
        model_tier: Tier,
        max_tokens: int,
    ) -> StructuredResult[Any]:
        self.requests.append(
            {"system": system, "messages": list(messages), "tier": model_tier, "max": max_tokens}
        )
        if not self.responses:
            raise AssertionError("FakeProvider sem resposta roteirizada")
        answer = self.responses.pop(0)
        if isinstance(answer, Exception):
            raise answer
        output = validate_output(schema, answer)
        usage = Usage(self.name, f"fake-{model_tier}", len(system) // 4, len(answer) // 4, 1)
        return StructuredResult(output, usage)

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        # Vetor estável derivado do texto: mesmo texto, mesmo vetor, em qualquer processo.
        return [
            [byte / 255 for byte in hashlib.sha256(text.encode()).digest()[:DIMENSIONS]]
            for text in texts
        ]
