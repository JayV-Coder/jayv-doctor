"""Validação e teste de conexão pelo conector do provedor, sem guardar nem logar a credencial."""

import asyncio
from collections.abc import Mapping
from typing import Any

from aid_connectors.base import Connector, Secret
from aid_connectors.registry import REGISTRY

from aid_api.connectors.schemas import TestResult
from aid_api.core.errors import ApiError

TEST_TIMEOUT = 15.0


def implementation(provider: str) -> Connector:
    found = REGISTRY.get(provider)
    if found is None:
        raise ApiError(422, "provider_unavailable", "Este provedor ainda não tem Conector.")
    return found()


def check_config(provider: str, config: Mapping[str, Any]) -> None:
    errors = implementation(provider).validate_config(config)
    if errors:
        # Só os nomes dos campos e as regras: os valores podem ser dados do cliente.
        detail = "; ".join(f"{field}: {rule}" for field, rule in sorted(errors.items()))
        raise ApiError(422, "invalid_config", f"Configuração inválida ({detail}).")


async def test_connection(provider: str, config: Mapping[str, Any], credential: str) -> TestResult:
    check_config(provider, config)
    connector = implementation(provider)
    try:
        result = await asyncio.wait_for(
            connector.test_connection(Secret(credential), config), TEST_TIMEOUT
        )
    except TimeoutError:
        return TestResult(ok=False, message="O provedor não respondeu a tempo.")
    return TestResult(ok=result.ok, message=result.message)
