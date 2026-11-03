"""Cache de respostas por hash de (provedor, modelo, prompt, entradas), por 24 h: a mesma
análise pedida de novo não paga de novo. A chave não guarda o conteúdo, só o hash."""

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

TTL_SECONDS = 24 * 3600
MAX_ENTRIES = 2000


def cache_key(
    scope: str,
    provider: str,
    model: str,
    system: str,
    parts: Sequence[Sequence[str]],
    schema: dict[str, Any],
) -> str:
    """`scope` é a Organização: duas Organizações com o mesmo log nunca dividem resposta."""
    payload = json.dumps(
        {
            "scope": scope,
            "provider": provider,
            "model": model,
            "system": system,
            "parts": [list(part) for part in parts],
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
    max_entries: int = MAX_ENTRIES
    clock: Callable[[], float] = time.monotonic
    entries: dict[str, tuple[float, str]] = field(default_factory=dict)

    async def get(self, key: str) -> str | None:
        found = self.entries.get(key)
        if found is None or self.clock() - found[0] > self.ttl_seconds:
            self.entries.pop(key, None)
            return None
        return found[1]

    async def put(self, key: str, value: str) -> None:
        now = self.clock()
        # Vencidos saem a cada gravação; acima do teto, saem os mais antigos.
        for stale in [k for k, (at, _) in self.entries.items() if now - at > self.ttl_seconds]:
            del self.entries[stale]
        while len(self.entries) >= self.max_entries:
            del self.entries[next(iter(self.entries))]
        self.entries[key] = (now, value)
