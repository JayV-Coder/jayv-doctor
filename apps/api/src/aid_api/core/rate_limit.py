"""Token bucket por tenant e Usuário, em memória por instância; o limite global é do Cloud Armor."""

import math
import os
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from aid_api.core.auth import Claims, get_claims
from aid_api.core.errors import ApiError


@dataclass
class Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    def __init__(
        self,
        capacity: int,
        per_minute: int,
        max_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.capacity = capacity
        self.rate = per_minute / 60
        self.max_keys = max_keys
        self.clock = clock
        self.buckets: OrderedDict[str, Bucket] = OrderedDict()

    def allow(self, key: str) -> float:
        """Devolve 0 se passou, ou os segundos até haver um token."""
        now = self.clock()
        bucket = self.buckets.pop(key, None) or Bucket(self.capacity, now)
        bucket.tokens = min(self.capacity, bucket.tokens + (now - bucket.updated_at) * self.rate)
        bucket.updated_at = now
        self.buckets[key] = bucket
        # A chave mais antiga sai: esquecer alguém só devolve o balde cheio.
        if len(self.buckets) > self.max_keys:
            self.buckets.popitem(last=False)
        if bucket.tokens < 1:
            return (1 - bucket.tokens) / self.rate
        bucket.tokens -= 1
        return 0


@lru_cache
def get_limiter() -> TokenBucketLimiter:
    per_minute = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "120"))
    return TokenBucketLimiter(per_minute, per_minute)


def rate_limit(
    claims: Annotated[Claims, Depends(get_claims)],
    limiter: Annotated[TokenBucketLimiter, Depends(get_limiter)],
) -> None:
    wait = limiter.allow(f"{claims.tenant_id}:{claims.sub}")
    if wait > 0:
        raise ApiError(
            429,
            "rate_limited",
            "Muitas requisições. Tente de novo em instantes.",
            {"Retry-After": str(math.ceil(wait))},
        )
