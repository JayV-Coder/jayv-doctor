"""Cache de respostas por hash de (provedor, modelo, prompt, entradas), por 24 h: a mesma
análise pedida de novo não paga de novo. A chave não guarda o conteúdo, só o hash."""

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from aid_diagnosis_engine.llm.base import Msg

TTL_SECONDS = 24 * 3600


def cache_key(
    provider: str, model: str, system: str, messages: Sequence[Msg], schema: dict[str, Any]
) -> str:
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "system": system,
            "messages": [[m.role, m.content] for m in messages],
            "schema": schema,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class ResponseCache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def put(self, key: str, value: str) -> None: ...


@dataclass
class MemoryCache:
    """Por processo; o worker de diagnóstico pode trocar por um cache no banco."""

    ttl_seconds: float = TTL_SECONDS
    clock: Callable[[], float] = time.monotonic
    entries: dict[str, tuple[float, str]] = field(default_factory=dict)

    async def get(self, key: str) -> str | None:
        found = self.entries.get(key)
        if found is None or self.clock() - found[0] > self.ttl_seconds:
            self.entries.pop(key, None)
            return None
        return found[1]

    async def put(self, key: str, value: str) -> None:
        self.entries[key] = (self.clock(), value)
