"""Timeout, retry com backoff em falha transitória e circuit breaker por provedor: com o
provedor fora, o diagnóstico cai rápido para o modo degradado (só Regras) em vez de esperar."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from aid_diagnosis_engine.llm.base import LLMTransientError, LLMUnavailableError


@dataclass
class CircuitBreaker:
    failures_to_open: int = 5
    cooldown_seconds: float = 60.0
    clock: Callable[[], float] = time.monotonic
    failures: int = 0
    opened_at: float | None = None

    def check(self) -> None:
        if self.opened_at is None:
            return
        if self.clock() - self.opened_at < self.cooldown_seconds:
            raise LLMUnavailableError("Provedor de IA indisponível no momento (circuito aberto).")
        # Meia-abertura: deixa uma chamada passar; se falhar, abre de novo.
        self.opened_at = None
        self.failures = self.failures_to_open - 1

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failures_to_open:
            self.opened_at = self.clock()


@dataclass
class RetryPolicy:
    attempts: int = 3
    base_seconds: float = 1.0
    max_seconds: float = 20.0
    timeout_seconds: float = 90.0
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    jitter: Callable[[], float] = field(default=random.random)

    def delay(self, attempt: int) -> float:
        ceiling = min(self.max_seconds, self.base_seconds * 2.0**attempt)
        return ceiling / 2 + ceiling / 2 * self.jitter()


async def resilient[R](
    call: Callable[[], Awaitable[R]], policy: RetryPolicy, breaker: CircuitBreaker
) -> R:
    for attempt in range(policy.attempts):
        breaker.check()
        try:
            result = await asyncio.wait_for(call(), policy.timeout_seconds)
        except (LLMTransientError, TimeoutError) as exc:
            breaker.failure()
            if attempt + 1 >= policy.attempts:
                raise LLMTransientError(
                    "O provedor de IA não respondeu depois das tentativas."
                ) from exc
            await policy.sleep(policy.delay(attempt))
            continue
        breaker.success()
        return result
    raise LLMTransientError("O provedor de IA não respondeu.")
