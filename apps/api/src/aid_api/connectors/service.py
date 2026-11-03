"""Validação e teste de conexão pelo conector do provedor, sem guardar nem logar a credencial."""

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from aid_connectors.base import Connector, ConnectorError, Secret
from aid_connectors.registry import REGISTRY

from aid_api.connectors.schemas import TestResult
from aid_api.core.errors import ApiError

logger = logging.getLogger(__name__)
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


async def test_connection(
    provider: str, config: Mapping[str, Any], credential: str, *, preview: bool
) -> TestResult:
    check_config(provider, config)
    connector = implementation(provider)
    try:
        result = await asyncio.wait_for(
            connector.test_connection(Secret(credential), config, preview=preview), TEST_TIMEOUT
        )
    except TimeoutError:
        return TestResult(ok=False, message="O provedor não respondeu a tempo.")
    except ConnectorError as exc:
        return TestResult(ok=False, message=exc.message)
    except Exception:
        # Erro de rede ou do conector: falha do teste, não da API. Sem detalhe, que pode ecoar a
        # credencial ou a resposta do provedor.
        logger.exception("teste de conexão do provedor %s falhou", provider)
        return TestResult(ok=False, message="Não foi possível falar com o provedor.")
    return TestResult(ok=result.ok, message=result.message)
