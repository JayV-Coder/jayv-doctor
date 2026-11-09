"""Conector fake (`provider = "fake"`), com falhas injetáveis pela config: timeout, 429, 401,
erro temporário e paginação quebrada. Serve aos testes e à suíte de contrato."""

import asyncio
from collections import Counter
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from aid_connectors.base import (
    Batch,
    Checkpoint,
    ConfigErrors,
    ConnectorError,
    RateLimitPolicy,
    Secret,
    TestResult,
    stable_uuid7,
)

START = datetime(2026, 11, 2, 14, 0, tzinfo=UTC)
MESSAGES = {
    "timeout": "O provedor demorou demais para responder.",
    "rate_limit": "O provedor limitou as chamadas (429).",
    "transient": "Falha temporária no provedor (503).",
    "auth": "Credencial recusada pelo provedor (401).",
    "api_limit": "Limite diário da API do provedor em 80%.",
}


class FakeConnector:
    provider: ClassVar[str] = "fake"
    rate_limit: ClassVar[RateLimitPolicy] = RateLimitPolicy(requests_per_minute=600)

    def __init__(self) -> None:
        self.failures: Counter[int] = Counter()

    def validate_config(self, config: Mapping[str, Any]) -> ConfigErrors:
        errors: ConfigErrors = {}
        pages, size = config.get("pages"), config.get("page_size", 1)
        if not isinstance(pages, int) or not 0 <= pages <= 1000:
            errors["pages"] = "de 0 a 1000"
        if not isinstance(size, int) or not 1 <= size <= 500:
            errors["page_size"] = "de 1 a 500"
        if "fail" in config and not isinstance(config["fail"], dict):
            errors["fail"] = "objeto {page, kind, times}"
        return errors

    async def test_connection(
        self, secret: Secret, config: Mapping[str, Any], *, preview: bool = False
    ) -> TestResult:
        fail = config.get("fail") or {}
        if not secret.reveal() or fail.get("kind") == "auth":
            return TestResult(False, MESSAGES["auth"])
        return TestResult(True, "Conexão estabelecida.")

    def event(self, page: int, index: int) -> dict[str, Any]:
        moment = START + timedelta(minutes=page, seconds=index)
        return {
            "schema_version": "1.0",
            "event_id": stable_uuid7(f"fake:{page}:{index}", moment),
            "timestamp": moment.isoformat(),
            "source": {"provider": "custom", "service": "fake"},
            "operation": "fake_operation",
            "severity": "ERROR" if index == 0 else "INFO",
            "execution_id": f"p{page}-{index}",
        }

    async def collect(
        self, secret: Secret, config: Mapping[str, Any], checkpoint: Checkpoint | None
    ) -> AsyncIterator[Batch]:
        start = int(checkpoint["page"]) if checkpoint else 0
        fail = config.get("fail") or {}
        for page in range(start + 1, int(config["pages"]) + 1):
            if fail.get("page") == page and self.failures[page] < int(fail.get("times", 1)):
                self.failures[page] += 1
                kind = fail["kind"]
                raise ConnectorError(kind, MESSAGES[kind], retry_after=None)
            if config.get("hang_seconds"):
                await asyncio.sleep(float(config["hang_seconds"]))
            events = [self.event(page, index) for index in range(int(config.get("page_size", 1)))]
            reached = start if config.get("broken_pagination") else page
            yield Batch(events, {"page": reached})
