"""Interface pequena de um Conector. Tudo o que é comum (retry, backoff, timeout, Checkpoint por
lote, política de falhas) fica no runtime, fora do conector."""

import hashlib
import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal, Protocol

Checkpoint = Mapping[str, Any]
ConfigErrors = dict[str, str]
# `quota`: a Cota de Eventos do mês da Organização acabou (#31); não é falha do Conector.
# `api_limit`: o limite diário de API do provedor chegou a 80% (#37); pausa até a janela seguinte.
ErrorKind = Literal["auth", "rate_limit", "timeout", "transient", "invalid", "quota", "api_limit"]


class Secret:
    """Credencial vinda do Vault. Não aparece em repr, log nem exceção."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(***)"

    __str__ = __repr__


@dataclass(frozen=True)
class RateLimitPolicy:
    requests_per_minute: int


@dataclass(frozen=True)
class TestResult:
    ok: bool
    message: str
    # Fontes que a conta do cliente oferece (ex.: EventLogFile só com Event Monitoring).
    capabilities: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class Batch:
    """Eventos no Contrato v1 (sem `integration_id`, que o runtime preenche) e o Checkpoint de
    depois deste lote. O runtime grava os dois juntos."""

    events: list[dict[str, Any]]
    checkpoint: Checkpoint
    meta: dict[str, Any] = field(default_factory=dict)


class ConnectorError(Exception):
    """Falha classificada pelo conector. A mensagem vai para o Usuário: nada de credencial."""

    def __init__(self, kind: ErrorKind, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.kind: ErrorKind = kind
        self.message = message
        self.retry_after = retry_after


class Connector(Protocol):
    provider: ClassVar[str]
    rate_limit: ClassVar[RateLimitPolicy]

    def validate_config(self, config: Mapping[str, Any]) -> ConfigErrors: ...

    async def test_connection(
        self, secret: Secret, config: Mapping[str, Any], *, preview: bool = False
    ) -> TestResult:
        """`preview`: além de testar, estima o volume com a config (assistente de criação)."""
        ...

    def collect(
        self, secret: Secret, config: Mapping[str, Any], checkpoint: Checkpoint | None
    ) -> AsyncIterator[Batch]: ...


def stable_uuid7(seed: str, moment: datetime) -> str:
    """UUIDv7 determinístico a partir do id na origem: o mesmo registro coletado de novo gera o
    mesmo event_id, e a deduplicação da ingestão o descarta."""
    millis = int(moment.timestamp() * 1000)
    rest = int.from_bytes(hashlib.sha256(seed.encode()).digest()[:10], "big")
    value = (millis << 80) | rest
    value = (value & ~(0xF << 76)) | (0x7 << 76)
    value = (value & ~(0x3 << 62)) | (0x2 << 62)
    return str(uuid.UUID(int=value))
