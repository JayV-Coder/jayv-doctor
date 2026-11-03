"""Executa uma Sincronização: retries com backoff exponencial e jitter, timeout por lote, prazo
total e Checkpoint gravado junto com cada lote (pelo `sink`). Depois de uma queda, a próxima
Sincronização retoma do último Checkpoint gravado; a deduplicação da ingestão (#12) cobre a
sobreposição."""

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from aid_connectors.base import Batch, Checkpoint, Connector, ConnectorError, ErrorKind, Secret

Sink = Callable[[Batch], Awaitable[None]]
# Erros em que repetir não adianta: precisa de ação humana ou de correção no conector.
FINAL: set[ErrorKind] = {"auth", "invalid"}
BROKEN = "O Checkpoint não avançou: a paginação do provedor está quebrada."


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 5
    base_seconds: float = 1.0
    max_seconds: float = 60.0
    batch_timeout: float = 60.0
    # Abaixo do timeout do worker (600 s) e do prazo da vez do Conector (10 min): o que passar
    # disso continua na próxima Sincronização, a partir do Checkpoint.
    deadline_seconds: float = 480.0


@dataclass(frozen=True)
class SyncResult:
    status: str
    records: int
    checkpoint_to: Checkpoint | None
    retries: int
    error_kind: ErrorKind | None = None
    error_message: str | None = None
    # Parou pelo prazo com lotes a coletar: o agendador volta logo, do Checkpoint.
    more: bool = False


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
    monotonic: Callable[[], float] = time.monotonic,
) -> SyncResult:
    records = retries = failures = 0
    current = checkpoint
    deadline = monotonic() + policy.deadline_seconds
    # Checkpoints já vistos: cursor que volta (A → B → A) é paginação quebrada, não progresso.
    seen = {json.dumps(checkpoint, sort_keys=True)}
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
                marker = json.dumps(batch.checkpoint, sort_keys=True)
                if marker in seen:
                    raise ConnectorError("invalid", BROKEN)
                seen.add(marker)
                # Erro do sink (banco, queda do worker) não é do provedor: sobe sem retry aqui.
                await sink(batch)
                current = batch.checkpoint
                records += len(batch.events)
                failures = 0
                if monotonic() >= deadline:
                    return SyncResult("succeeded", records, current, retries, more=True)
        except ConnectorError as exc:
            failures += 1
            if exc.kind in FINAL or failures >= policy.attempts:
                return SyncResult("failed", records, current, retries, exc.kind, exc.message)
            retries += 1
            # Retry-After do provedor vale, mas nunca além do máximo da política.
            wait = min(exc.retry_after, policy.max_seconds) if exc.retry_after else None
            await sleep(wait or backoff(policy, failures, jitter()))
