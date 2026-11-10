"""Verificação diária dos perfis de IA (#45): hosts e região efetivos de cada perfil em uso."""

import logging
import os
from collections.abc import Sequence
from typing import Any

import httpx
import pytest
from aid_diagnosis_engine.llm import egress
from aid_diagnosis_engine.llm.base import InputType, LLMProvider, StructuredResult, Usage
from aid_diagnosis_engine.llm.vertex import VertexProvider
from aid_diagnosis_worker.ai_verify import Probe, expected, verify_profiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")


class Recording:
    """Provedor que registra o egress num host escolhido (sem rede)."""

    def __init__(self, name: str, host: str) -> None:
        self.name, self.host = name, host
        self.embedding_model, self.embedding_dimensions = "fake", 8

    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        egress.record(self.name, self.host)
        return [[0.0] * 8 for _ in texts]

    async def complete_structured(self, **kwargs: Any) -> StructuredResult[Any]:
        egress.record(self.name, self.host)
        return StructuredResult(Probe(ok=True), Usage(self.name, "fake", 1, 1, 1))


async def run(engine: AsyncEngine, sql: str, **params: Any) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(sql), params)


def vertex() -> VertexProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == egress.METADATA_HOST:
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        if request.url.path.endswith(":predict"):
            return httpx.Response(200, json={"predictions": [{"embeddings": {"values": [0.1]}}]})
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": '{"ok": true}'}]}, "finishReason": "STOP"}
                ]
            },
        )

    return VertexProvider(project="aid-prd", transport=httpx.MockTransport(handler))


def test_hosts_esperados_por_perfil() -> None:
    br = ["metadata.google.internal", "southamerica-east1-aiplatform.googleapis.com"]
    assert expected("br_region", br) is None
    assert "fora do Brasil" in (expected("br_region", ["api.voyageai.com"]) or "")
    assert expected("standard", ["api.anthropic.com", "api.voyageai.com"]) is None
    assert expected("dedicated", []) == "nenhuma chamada saiu"


@pytest.mark.asyncio
async def test_perfil_brasil_verificado_e_divergencia_alerta(
    engine: AsyncEngine, tenant: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    await run(
        engine,
        "update doctor.tenants set ai_profile = 'br_region' where id = :t",
        t=tenant["tenant"],
    )
    good: dict[str, LLMProvider] = {
        "anthropic": Recording("anthropic", "api.anthropic.com"),
        "vertex": vertex(),
        "vertex_dedicated": vertex(),
    }
    results = await verify_profiles(engine, lambda name, project: good[name])
    [brazil] = [r for r in results if r["profile"] == "br_region"]
    assert brazil["ok"]
    assert set(brazil["hosts"]) <= {
        egress.METADATA_HOST,
        "southamerica-east1-aiplatform.googleapis.com",
    }
    async with engine.begin() as connection:
        region = await connection.scalar(
            text(
                "select region from doctor.ai_profile_checks where profile = 'br_region'"
                " order by checked_at desc, id desc limit 1"
            )
        )
    assert region == "southamerica-east1"

    # O provedor do Brasil passou a usar um host fora dele: a verificação registra e alerta.
    bad = {**good, "vertex": Recording("vertex", "us-central1-aiplatform.googleapis.com")}
    caplog.set_level(logging.ERROR)
    results = await verify_profiles(engine, lambda name, project: bad[name])
    [brazil] = [r for r in results if r["profile"] == "br_region"]
    assert not brazil["ok"]
    assert any(r.getMessage() == "ai.profile_divergence" for r in caplog.records)


class Refused(Recording):
    async def complete_structured(self, **kwargs: Any) -> StructuredResult[Any]:
        from aid_diagnosis_engine.llm.base import LLMTransientError

        egress.record(self.name, self.host)
        raise LLMTransientError("Vertex AI respondeu HTTP 429.")


class Broken(Recording):
    async def embed(self, texts: Sequence[str], *, input_type: InputType) -> list[list[float]]:
        raise KeyError("predictions")


@pytest.mark.asyncio
async def test_falha_no_brasil_nao_e_divergencia_e_erro_nao_para_os_outros(
    engine: AsyncEngine, tenant: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    await run(
        engine,
        "update doctor.tenants set ai_profile = 'br_region' where id = :t",
        t=tenant["tenant"],
    )
    providers: dict[str, Any] = {
        # O dedicado sem capacidade: 429 com o host no Brasil.
        "vertex": Refused("vertex", "southamerica-east1-aiplatform.googleapis.com"),
        # O padrão quebra com um erro que não é do LLM: os outros seguem.
        "anthropic": Broken("anthropic", "api.anthropic.com"),
        "vertex_dedicated": vertex(),
    }
    caplog.set_level(logging.WARNING)
    results = await verify_profiles(engine, lambda name, project: providers[name])
    by_profile = {r["profile"]: r for r in results}
    assert (by_profile["br_region"]["ok"], by_profile["br_region"]["in_region"]) == (False, True)
    if "standard" in by_profile:
        assert by_profile["standard"]["ok"] is False
    messages = {r.getMessage() for r in caplog.records}
    assert "ai.profile_check_failed" in messages
    assert "ai.profile_divergence" not in messages
