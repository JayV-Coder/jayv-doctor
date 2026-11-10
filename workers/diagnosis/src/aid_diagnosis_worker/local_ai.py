"""Perfil `local` (ticket #46, ADR-0019): monta o `LocalProvider` com a configuração da
Organização. Pelo agente, o pedido vai para `doctor.local_llm_requests` e o worker espera a
resposta que o agente devolve (long-poll do agente, só de saída); a linha sai ao ser lida.
Pelo endpoint privado, a chamada é direta, só para aquele host."""

import asyncio
import json
import time
from functools import cache
from typing import Any

from aid_db import platform_role
from aid_diagnosis_engine.llm.base import LLMUnavailableError
from aid_diagnosis_engine.llm.local import LocalProvider, PrivateEndpoint
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

POLL_SECONDS = 0.5


class AgentRelay:
    """O modelo local pelo agente da Organização."""

    def __init__(
        self,
        engine: AsyncEngine,
        tenant: str,
        agent: str,
        timeout: float,
        poll: float = POLL_SECONDS,
    ) -> None:
        self.engine, self.tenant, self.agent = engine, tenant, agent
        self.timeout, self.poll = timeout, poll

    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        async with self.engine.begin() as db:
            await platform_role(db)
            request = await db.scalar(
                text(
                    "insert into doctor.local_llm_requests (tenant_id, agent_id, request)"
                    " values (cast(:t as uuid), cast(:a as uuid), cast(:r as jsonb))"
                    " returning id::text"
                ),
                {"t": self.tenant, "a": self.agent, "r": json.dumps(body)},
            )
        deadline = time.monotonic() + self.timeout
        try:
            while time.monotonic() < deadline:
                async with self.engine.begin() as db:
                    await platform_role(db)
                    row = (
                        await db.execute(
                            text(
                                "select status, response, error from doctor.local_llm_requests"
                                " where id = cast(:r as uuid)"
                            ),
                            {"r": request},
                        )
                    ).first()
                if row is None:
                    break
                if row.status == "done" and isinstance(row.response, dict):
                    return dict(row.response)
                if row.status in ("done", "failed"):
                    raise LLMUnavailableError(
                        f"O modelo local falhou: {row.error or 'resposta vazia'}"[:300]
                    )
                await asyncio.sleep(self.poll)
            raise LLMUnavailableError("O agente não trouxe a resposta do modelo local a tempo.")
        finally:
            # A linha sai sempre: nem o prompt nem a resposta ficam no banco.
            async with self.engine.begin() as db:
                await platform_role(db)
                await db.execute(
                    text("delete from doctor.local_llm_requests where id = cast(:r as uuid)"),
                    {"r": request},
                )


async def local_provider(engine: AsyncEngine, tenant: str) -> LocalProvider | None:
    """`None` sem configuração: o Diagnóstico sai só com as Regras (nunca em nuvem)."""
    async with engine.begin() as db:
        await platform_role(db)
        found = (
            await db.execute(
                text(
                    "select transport, agent_id::text, endpoint_url, model, timeout_seconds"
                    " from doctor.local_ai_settings where tenant_id = cast(:t as uuid)"
                ),
                {"t": tenant},
            )
        ).first()
    if found is None:
        return None
    timeout = float(found.timeout_seconds)
    if found.transport == "agent":
        relay = AgentRelay(engine, tenant, found.agent_id, timeout)
        return LocalProvider(relay, found.model, timeout)
    return LocalProvider(endpoint(found.endpoint_url, timeout), found.model, timeout)


@cache
def endpoint(url: str, timeout: float) -> PrivateEndpoint:
    """Um cliente HTTP por endereço privado e processo, como o registro dos provedores."""
    return PrivateEndpoint(url, timeout)


async def purge_local_requests(engine: AsyncEngine) -> int:
    """Pedidos esquecidos (worker derrubado no meio da espera): o prompt não fica no banco. O
    prazo máximo é de 10 min; passados 15, ninguém espera mais por eles."""
    async with engine.begin() as db:
        await platform_role(db)
        result = await db.execute(
            text(
                "delete from doctor.local_llm_requests"
                " where created_at < now() - interval '15 minutes'"
            )
        )
    return result.rowcount or 0
