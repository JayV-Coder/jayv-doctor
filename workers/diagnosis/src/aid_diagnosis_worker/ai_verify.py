"""Verificação diária dos perfis de IA (ticket #45, ADR-0018): para cada perfil em uso (e cada
projeto dedicado), uma pergunta fixa e um embedding, sem dado de cliente. Confere os hosts e a
região que as chamadas realmente usaram, grava em `doctor.ai_profile_checks` e, se divergir do
perfil, registra `ai.profile_divergence`, que dispara o alerta."""

import logging
from collections.abc import Callable
from typing import Any

from aid_db import platform_role
from aid_diagnosis_engine.llm import egress
from aid_diagnosis_engine.llm.base import LLMError, LLMProvider, Msg
from aid_diagnosis_engine.llm.registry import PROFILES
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)
ProviderFor = Callable[[str, str | None], LLMProvider]
BR_REGIONS = {egress.BR_REGION, "local"}
QUESTION = "Verificação diária do Integration AI Doctor: responda ok = true."


class Probe(BaseModel):
    ok: bool


def expected(profile: str, hosts: list[str]) -> str | None:
    """O motivo da divergência, ou `None` se os hosts batem com o perfil."""
    if not hosts:
        return "nenhuma chamada saiu"
    regions = {egress.region_of(host) for host in hosts}
    if profile in ("br_region", "dedicated") and not regions <= BR_REGIONS:
        return f"região fora do Brasil: {', '.join(sorted(regions - BR_REGIONS))}"
    if profile == "standard" and not set(hosts) <= egress.US_HOSTS:
        return f"host inesperado: {', '.join(sorted(set(hosts) - egress.US_HOSTS))}"
    return None


async def check(provider: LLMProvider, profile: str) -> tuple[bool, list[str], str | None]:
    with egress.recording() as hosts:
        try:
            await provider.embed([QUESTION], input_type="query")
            await provider.complete_structured(
                system="Responda só no formato pedido.",
                messages=[Msg("user", QUESTION)],
                schema=Probe,
                model_tier="fast",
                max_tokens=32,
            )
            failure = None
        except LLMError as exc:
            failure = f"a chamada falhou: {exc}"[:300]
    divergence = expected(profile, hosts) if failure is None or hosts else None
    return failure is None and divergence is None, sorted(set(hosts)), divergence or failure


async def verify_profiles(engine: AsyncEngine, provider_for: ProviderFor) -> list[dict[str, Any]]:
    async with engine.begin() as connection:
        await platform_role(connection)
        targets = (
            await connection.execute(
                text(
                    "select distinct ai_profile, ai_project from doctor.tenants"
                    " where llm_enabled and deletion_requested_at is null"
                    " order by ai_profile, ai_project nulls first"
                )
            )
        ).all()
    results: list[dict[str, Any]] = []
    for profile, project in targets:
        ok, hosts, detail = await check(provider_for(PROFILES[profile], project), profile)
        regions = sorted({egress.region_of(host) for host in hosts} - {"local"})
        target = project or "platform"
        async with engine.begin() as connection:
            await platform_role(connection)
            await connection.execute(
                text(
                    "insert into doctor.ai_profile_checks (profile, target, ok, hosts, region,"
                    " detail) values (:p, :t, :ok, :h, :r, :d)"
                ),
                {
                    "p": profile,
                    "t": target,
                    "ok": ok,
                    "h": hosts,
                    "r": ", ".join(regions) or None,
                    "d": detail,
                },
            )
        if not ok:
            log.error(
                "ai.profile_divergence",
                extra={"fields": {"profile": profile, "target": target, "detail": detail or ""}},
            )
        results.append({"profile": profile, "target": target, "ok": ok, "hosts": hosts})
    return results
