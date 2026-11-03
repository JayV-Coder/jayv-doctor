"""Embeddings da Voyage (`voyage-3`, 1024 dimensões), parceira de embeddings da Anthropic. A
dimensão é registrada com cada vetor: trocar de modelo exige reindexar (#26)."""

import os
from collections.abc import Sequence

import httpx

from aid_diagnosis_engine.llm.base import InputType, LLMTransientError, LLMUnavailableError

URL = "https://api.voyageai.com/v1/embeddings"
MODEL = "voyage-3"
DIMENSIONS = 1024


class VoyageEmbeddings:
    dimensions = DIMENSIONS

    def __init__(
        self, api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("VOYAGE_API_KEY", "")
        self.transport = transport

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        if not texts:
            return []
        if not self.api_key:
            raise LLMUnavailableError("VOYAGE_API_KEY não configurada.")
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=httpx.Timeout(30.0)
            ) as client:
                response = await client.post(
                    URL,
                    headers={"authorization": f"Bearer {self.api_key}"},
                    json={"input": list(texts), "model": MODEL, "input_type": input_type},
                )
        except httpx.HTTPError as exc:
            raise LLMTransientError("Voyage não respondeu.") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise LLMTransientError(f"Voyage respondeu HTTP {response.status_code}.")
        if response.status_code != 200:
            raise LLMUnavailableError(f"Voyage recusou o pedido (HTTP {response.status_code}).")
        data = sorted(response.json()["data"], key=lambda item: item["index"])
        return [list(map(float, item["embedding"])) for item in data]
