"""Executa uma Sincronização: retries com backoff exponencial e jitter, timeout por lote e
Checkpoint gravado junto com cada lote (pelo `sink`). Depois de uma queda, a próxima Sincronização
retoma do último Checkpoint gravado; a deduplicação da ingestão (#12) cobre a sobreposição."""

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from aid_connectors.base import Batch, Checkpoint, Connector, ConnectorError, ErrorKind, Secret

Sink = Callable[[Batch], Awaitable[None]]
# Erros em que repetir não adianta: precisa de ação humana ou de correção no conector.
FINAL: set[ErrorKind] = {"auth", "invalid"}


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 5
    base_seconds: float = 1.0
    max_seconds: float = 60.0
    batch_timeout: float = 60.0


@dataclass(frozen=True)
class SyncResult:
    status: str
    records: int
    checkpoint_to: Checkpoint | None
    retries: int
    error_kind: ErrorKind | None = None
    error_message: str | None = None


DEFAULT_POLICY = RetryPolicy()


def backoff(policy: RetryPolicy, failures: int, jitter: float) -> float:
    """Exponencial com jitter "igual" (metade fixa, metade aleatória), limitado por `max`."""
    ceiling = min(policy.max_seconds, policy.base_seconds * 2.0 ** (failures - 1))
    return ceiling / 2 + ceiling / 2 * jitter


async def run_sync(
    connector: Connector,
    secret: str,
    config: Mapping[str, Any],
    checkpoint: Checkpoint | None,
    sink: Sink,
    policy: RetryPolicy = DEFAULT_POLICY,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[], float] = random.random,
) -> SyncResult:
    records = retries = failures = 0
    current = checkpoint
    while True:
        try:
            batches = connector.collect(Secret(secret), config, current).__aiter__()
            while True:
                try:
                    batch = await asyncio.wait_for(anext(batches), policy.batch_timeout)
                except StopAsyncIteration:
                    return SyncResult("succeeded", records, current, retries)
                except TimeoutError as exc:
                    raise ConnectorError(
                        "timeout", "O provedor demorou demais para responder."
                    ) from exc
                if batch.checkpoint == current:
                    raise ConnectorError(
                        "invalid",
                        "O Checkpoint não avançou: a paginação do provedor está quebrada.",
                    )
                # Erro do sink (banco, queda do worker) não é do provedor: sobe sem retry aqui.
                await sink(batch)
                current = batch.checkpoint
                records += len(batch.events)
                failures = 0
        except ConnectorError as exc:
            failures += 1
            if exc.kind in FINAL or failures >= policy.attempts:
                return SyncResult("failed", records, current, retries, exc.kind, exc.message)
            retries += 1
            await sleep(exc.retry_after or backoff(policy, failures, jitter()))
