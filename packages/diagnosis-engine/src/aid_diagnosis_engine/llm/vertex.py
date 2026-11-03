"""Gemini no Vertex AI, em southamerica-east1 (provedor alternativo, ADR-0007): para quem
precisa que os dados não saiam da região. Autenticação pela conta de serviço do Cloud Run
(servidor de metadados); saída em JSON com `responseJsonSchema`, validada de novo pelo Pydantic.
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
from aid_diagnosis_engine.llm.guards import token_batches

REGION = "southamerica-east1"
MODELS: dict[Tier, str] = {"reasoning": "gemini-2.5-pro", "fast": "gemini-2.5-flash"}
# O Gemini 2.5 pensa antes de responder e esse pensamento sai do mesmo teto de tokens: um
# orçamento fixo, somado ao teto pedido, impede que a resposta saia cortada.
THINKING_BUDGET: dict[Tier, int] = {"reasoning": 2048, "fast": 0}
EMBEDDING_MODEL = "text-embedding-005"
DIMENSIONS = 768
# Limites do text-embedding-005 por pedido: 250 textos e 20 mil tokens (com folga).
EMBED_BATCH = 250
EMBED_BATCH_TOKENS = 15_000
METADATA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
TASKS: dict[InputType, str] = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}
# Bloqueio de segurança do Gemini: é recusa (modo degradado), não saída inválida.
REFUSALS = {"SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"}


class VertexProvider:
    name = "vertex"
    embedding_dimensions = DIMENSIONS
    embedding_model = EMBEDDING_MODEL

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
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Um cliente por instância (e o registro guarda uma instância por processo): a conexão
        TLS é reaproveitada."""
        if self._client is None:
            self._client = httpx.AsyncClient(transport=self.transport, timeout=httpx.Timeout(90.0))
        return self._client

    def base(self, model: str) -> str:
        return (
            f"https://{self.region}-aiplatform.googleapis.com/v1/projects/{self.project}"
            f"/locations/{self.region}/publishers/google/models/{model}"
        )

    async def bearer(self) -> str:
        if self.token is None or self.token[1] < time.monotonic() + 60:
            try:
                response = await self.client.get(
                    METADATA_URL, headers={"metadata-flavor": "Google"}
                )
            except httpx.HTTPError as exc:
                # Fora do GCP ou sem conta de serviço: repetir não traz a credencial.
                raise LLMUnavailableError(
                    "Sem credencial do Google Cloud para o Vertex AI."
                ) from exc
            if response.status_code != 200:
                raise LLMUnavailableError("Sem credencial do Google Cloud para o Vertex AI.")
            body = response.json()
            self.token = (str(body["access_token"]), time.monotonic() + float(body["expires_in"]))
        return self.token[0]

    async def post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.project:
            raise LLMUnavailableError("GCP_PROJECT_ID não configurado para o Vertex AI.")
        token = await self.bearer()
        try:
            response = await self.client.post(
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
        thinking = THINKING_BUDGET[model_tier]
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
                "maxOutputTokens": max_tokens + thinking,
                "thinkingConfig": {"thinkingBudget": thinking},
            },
        }
        found = await self.post(f"{self.base(model)}:generateContent", body)
        metadata = found.get("usageMetadata", {})
        usage = Usage(
            provider=self.name,
            model=model,
            input_tokens=int(metadata.get("promptTokenCount", 0)),
            # O pensamento também é cobrado como saída.
            output_tokens=int(metadata.get("candidatesTokenCount", 0))
            + int(metadata.get("thoughtsTokenCount", 0)),
            latency_ms=round((time.monotonic() - start) * 1000),
        )
        candidates = found.get("candidates") or []
        if not candidates or candidates[0].get("finishReason") in REFUSALS:
            raise LLMUnavailableError("O modelo recusou a análise.", usage)
        first = candidates[0]
        if first.get("finishReason") == "MAX_TOKENS":
            raise LLMInvalidOutputError("resposta cortada pelo limite de tokens", usage)
        text = "".join(part.get("text", "") for part in first.get("content", {}).get("parts", []))
        return StructuredResult(validate_output(schema, text, usage), usage)

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in token_batches(texts, EMBED_BATCH, EMBED_BATCH_TOKENS):
            found = await self.post(
                f"{self.base(EMBEDDING_MODEL)}:predict",
                {
                    "instances": [
                        {"content": text, "task_type": TASKS[input_type]} for text in batch
                    ]
                },
            )
            vectors.extend(
                list(map(float, p["embeddings"]["values"])) for p in found["predictions"]
            )
        return vectors
