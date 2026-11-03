"""Gemini no Vertex AI, em southamerica-east1 (provedor alternativo, ADR-0007): para quem
precisa que os dados não saiam da região. Autenticação pela conta de serviço do Cloud Run
(servidor de metadados); saída em JSON com `responseSchema`, validada de novo pelo Pydantic.
Embeddings `text-embedding-005` (768 dimensões).
"""

import os
import time
from collections.abc import Sequence
from typing import Any

import httpx

from aid_diagnosis_engine.llm.base import (
    InputType,
    LLMInvalidOutputError,
    LLMTransientError,
    LLMUnavailableError,
    Msg,
    StructuredResult,
    Tier,
    Usage,
)
from aid_diagnosis_engine.llm.client import validate_output

REGION = "southamerica-east1"
MODELS: dict[Tier, str] = {"reasoning": "gemini-2.5-pro", "fast": "gemini-2.5-flash"}
EMBEDDING_MODEL = "text-embedding-005"
DIMENSIONS = 768
METADATA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
TASKS: dict[InputType, str] = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}


class VertexProvider:
    name = "vertex"
    embedding_dimensions = DIMENSIONS

    def __init__(
        self,
        project: str | None = None,
        region: str = REGION,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.project = project or os.environ.get("GCP_PROJECT_ID", "")
        self.region = region
        self.transport = transport
        self.token: tuple[str, float] | None = None

    def base(self, model: str) -> str:
        return (
            f"https://{self.region}-aiplatform.googleapis.com/v1/projects/{self.project}"
            f"/locations/{self.region}/publishers/google/models/{model}"
        )

    async def bearer(self, client: httpx.AsyncClient) -> str:
        if self.token is None or self.token[1] < time.monotonic() + 60:
            response = await client.get(METADATA_URL, headers={"metadata-flavor": "Google"})
            if response.status_code != 200:
                raise LLMUnavailableError("Sem credencial do Google Cloud para o Vertex AI.")
            body = response.json()
            self.token = (str(body["access_token"]), time.monotonic() + float(body["expires_in"]))
        return self.token[0]

    async def post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.project:
            raise LLMUnavailableError("GCP_PROJECT_ID não configurado para o Vertex AI.")
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=httpx.Timeout(90.0)
            ) as client:
                token = await self.bearer(client)
                response = await client.post(
                    url, json=body, headers={"authorization": f"Bearer {token}"}
                )
        except httpx.HTTPError as exc:
            raise LLMTransientError("Vertex AI não respondeu.") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise LLMTransientError(f"Vertex AI respondeu HTTP {response.status_code}.")
        if response.status_code != 200:
            raise LLMUnavailableError(f"Vertex AI recusou o pedido (HTTP {response.status_code}).")
        found: dict[str, Any] = response.json()
        return found

    async def complete_structured(
        self,
        *,
        system: str,
        messages: Sequence[Msg],
        schema: type[Any],
        model_tier: Tier,
        max_tokens: int,
    ) -> StructuredResult[Any]:
        model = MODELS[model_tier]
        start = time.monotonic()
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in messages
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema.model_json_schema(),
                "maxOutputTokens": max_tokens,
            },
        }
        found = await self.post(f"{self.base(model)}:generateContent", body)
        candidates = found.get("candidates") or []
        if not candidates:
            raise LLMUnavailableError("O modelo recusou a análise.")
        first = candidates[0]
        if first.get("finishReason") == "MAX_TOKENS":
            raise LLMInvalidOutputError("resposta cortada pelo limite de tokens")
        text = "".join(part.get("text", "") for part in first.get("content", {}).get("parts", []))
        output = validate_output(schema, text)
        usage = found.get("usageMetadata", {})
        return StructuredResult(
            output,
            Usage(
                provider=self.name,
                model=model,
                input_tokens=int(usage.get("promptTokenCount", 0)),
                output_tokens=int(usage.get("candidatesTokenCount", 0)),
                latency_ms=round((time.monotonic() - start) * 1000),
            ),
        )

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        if not texts:
            return []
        found = await self.post(
            f"{self.base(EMBEDDING_MODEL)}:predict",
            {"instances": [{"content": text, "task_type": TASKS[input_type]} for text in texts]},
        )
        return [list(map(float, p["embeddings"]["values"])) for p in found["predictions"]]
