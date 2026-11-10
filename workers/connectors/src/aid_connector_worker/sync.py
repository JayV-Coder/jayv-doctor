"""Uma Sincronização: pega a vez do Conector, lê a credencial no Vault, roda o conector pelo
runtime e grava cada lote junto com o Checkpoint. Os lotes seguem o pipeline do #12
(`ingestion_batches` + `ingestion.raw`), que sanitiza, valida e deduplica.

Política de falhas: erro de autenticação pausa até ação humana; 3 falhas seguidas marcam
`failing` e reagendam com backoff até 1 h. Job de plataforma: `service_role`.
"""

import json
import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from aid_connectors.base import Batch, Connector
from aid_connectors.runtime import RetryPolicy, SyncResult, run_sync
from aid_db import platform_role
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)
# Sincronização em `running` há mais que isso é de um worker que morreu.
LEASE = timedelta(minutes=10)
FAILING_AFTER = 3
MAX_BACKOFF_SECONDS = 3600
RETRY_SOON_SECONDS = 60


async def claim(engine: AsyncEngine, connector_id: str) -> tuple[Mapping[str, Any], str] | str:
    """(Conector, id da Sincronização) ou o motivo de não rodar: `ignored` ou `busy`."""
    async with engine.begin() as connection:
        await platform_role(connection)
        found = (
            (
                await connection.execute(
                    text(
                        "select id::text, tenant_id::text, integration_id::text, provider, config,"
                        " status, checkpoint, config_version from doctor.connectors"
                        " where id = cast(:c as uuid) for update"
                    ),
                    {"c": connector_id},
                )
            )
            .mappings()
            .first()
        )
        if found is None or found["status"] in ("paused", "disabled"):
            return "ignored"
        running = await connection.scalar(
            text(
                "select count(*) from doctor.connector_syncs where tenant_id = cast(:t as uuid)"
                " and connector_id = cast(:c as uuid) and status = 'running'"
                " and started_at > now() - cast(:lease as interval)"
            ),
            {"t": found["tenant_id"], "c": connector_id, "lease": LEASE},
        )
        if running:
            return "busy"
        await connection.execute(
            text(
                "update doctor.connector_syncs set status = 'failed', finished_at = now(),"
                " error = 'Sincronização interrompida'"
                " where tenant_id = cast(:t as uuid) and connector_id = cast(:c as uuid)"
                " and status = 'running'"
            ),
            {"t": found["tenant_id"], "c": connector_id},
        )
        sync_id = await connection.scalar(
            text(
                "insert into doctor.connector_syncs (tenant_id, connector_id, checkpoint_from)"
                " values (cast(:t as uuid), cast(:c as uuid), cast(:cp as jsonb))"
                " returning id::text"
            ),
            {
                "t": found["tenant_id"],
                "c": connector_id,
                "cp": json.dumps(found["checkpoint"]) if found["checkpoint"] is not None else None,
            },
        )
        return dict(found), str(sync_id)


async def store_batch(
    engine: AsyncEngine, connector: Mapping[str, Any], sync_id: str, batch: Batch
) -> None:
    """Lote, mensagem e Checkpoint numa transação: depois de uma queda, nada se perde e o que se
    repetir a deduplicação da ingestão descarta."""
    events = [{**event, "integration_id": connector["integration_id"]} for event in batch.events]
    async with engine.begin() as connection:
        await platform_role(connection)
        batch_id = await connection.scalar(
            text(
                "insert into doctor.ingestion_batches"
                " (tenant_id, integration_id, connector_id, events, event_count)"
                " values (cast(:t as uuid), cast(:i as uuid), cast(:c as uuid),"
                " cast(:e as jsonb), :n) returning id::text"
            ),
            {
                "t": connector["tenant_id"],
                "i": connector["integration_id"],
                "c": connector["id"],
                "e": json.dumps(events),
                "n": len(events),
            },
        )
        await connection.execute(
            text(
                "insert into doctor.outbox_messages (tenant_id, topic, payload)"
                " values (cast(:t as uuid), 'ingestion.raw', cast(:p as jsonb))"
            ),
            {"t": connector["tenant_id"], "p": json.dumps({"batch_id": batch_id})},
        )
        await connection.execute(
            text(
                # Só se a config não mudou desde o começo: config nova recomeça do zero.
                "update doctor.connectors set checkpoint = cast(:cp as jsonb)"
                " where id = cast(:c as uuid) and config_version = :v"
            ),
            {
                "cp": json.dumps(batch.checkpoint),
                "c": connector["id"],
                "v": connector["config_version"],
            },
        )
        await connection.execute(
            text(
                "update doctor.connector_syncs set records = records + :n,"
                " checkpoint_to = cast(:cp as jsonb) where id = cast(:s as uuid)"
            ),
            {"n": len(events), "cp": json.dumps(batch.checkpoint), "s": sync_id},
        )


def next_status(result: SyncResult, failures: int) -> tuple[str, int]:
    """(status do Conector, segundos até a próxima tentativa) depois de uma falha."""
    if result.error_kind == "auth":
        return "paused", 0
    if failures >= FAILING_AFTER:
        backoff = RETRY_SOON_SECONDS * 5 * 2 ** (failures - FAILING_AFTER)
        return "failing", min(backoff, MAX_BACKOFF_SECONDS)
    return "active", RETRY_SOON_SECONDS


async def finish(
    engine: AsyncEngine, connector: Mapping[str, Any], sync_id: str, result: SyncResult
) -> None:
    async with engine.begin() as connection:
        await platform_role(connection)
        await connection.execute(
            text(
                "update doctor.connector_syncs set status = :status, finished_at = now(),"
                " error = :error where id = cast(:s as uuid)"
            ),
            {"status": result.status, "error": result.error_message, "s": sync_id},
        )
        if result.error_kind == "api_limit":
            # Limite diário do provedor (#37): a próxima rodada fica para depois da janela, sem
            # contar falha nem mudar o status. `paused_reason` só mostra o motivo na tela; uma
            # pausa manual ou desativação feita durante a Sincronização continua valendo.
            await connection.execute(
                text(
                    "update doctor.connectors set last_error = :error,"
                    " paused_reason = case when status in ('paused', 'disabled')"
                    " then paused_reason else 'api_limit' end,"
                    " next_run_at = now() + make_interval(secs => :seconds)"
                    " where id = cast(:c as uuid)"
                ),
                {
                    "error": result.error_message,
                    "seconds": result.retry_after or 3600,
                    "c": connector["id"],
                },
            )
            return
        if result.error_kind == "quota":
            # Cota acabou: o Conector não falhou. Sem contar falha nem backoff; tenta de hora em
            # hora (a Cota volta no mês seguinte ou com o aumento do plano).
            await connection.execute(
                text(
                    "update doctor.connectors set last_error = :error,"
                    " next_run_at = now() + interval '1 hour' where id = cast(:c as uuid)"
                ),
                {"error": result.error_message, "c": connector["id"]},
            )
            return
        if result.status == "succeeded":
            # Pausa ou desativação feitas durante a Sincronização valem: o status não volta.
            await connection.execute(
                text(
                    "update doctor.connectors set consecutive_failures = 0,"
                    " status = case when status in ('paused', 'disabled') then status"
                    " else 'active' end,"
                    " last_sync_at = now(), last_error = null,"
                    " paused_reason = case when paused_reason = 'api_limit' then null"
                    " else paused_reason end,"
                    " next_run_at = now() + make_interval(secs =>"
                    " case when :more then :soon else sync_interval_seconds end)"
                    " where id = cast(:c as uuid)"
                ),
                {"c": connector["id"], "more": result.more, "soon": RETRY_SOON_SECONDS},
            )
            return
        failures = int(
            await connection.scalar(
                text(
                    "update doctor.connectors set consecutive_failures = consecutive_failures + 1,"
                    " last_error = :error where id = cast(:c as uuid)"
                    " returning consecutive_failures"
                ),
                {"error": result.error_message, "c": connector["id"]},
            )
            or 0
        )
        status, seconds = next_status(result, failures)
        await connection.execute(
            text(
                "update doctor.connectors set"
                " status = case when status = 'disabled' then status else :status end,"
                " paused_reason = case when :status = 'paused' and status <> 'disabled'"
                " then 'auth' else paused_reason end,"
                " next_run_at = now() + make_interval(secs => :seconds)"
                " where id = cast(:c as uuid)"
            ),
            {"status": status, "seconds": seconds, "c": connector["id"]},
        )


async def secret_of(engine: AsyncEngine, connector_id: str) -> str:
    async with engine.begin() as connection:
        await platform_role(connection)
        return str(
            await connection.scalar(
                text("select doctor.get_connector_secret(cast(:c as uuid))"), {"c": connector_id}
            )
        )


QUOTA_EXCEEDED = "DR050"


async def sync_connector(
    payload: Mapping[str, Any],
    engine: AsyncEngine,
    registry: Mapping[str, type[Connector]],
    policy: RetryPolicy,
) -> str:
    """`succeeded`, `failed` (registrado), `busy` (outra Sincronização em curso) ou `ignored`."""
    claimed = await claim(engine, str(payload["connector_id"]))
    if isinstance(claimed, str):
        return claimed
    connector, sync_id = claimed
    try:
        result = await execute(engine, registry, policy, connector, sync_id)
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) != QUOTA_EXCEEDED:
            raise
        result = SyncResult(
            "failed",
            0,
            connector["checkpoint"],
            0,
            "quota",
            "Cota de Eventos do mês esgotada: a coleta volta com o próximo mês ou o aumento"
            " do plano.",
        )
    except Exception:
        # Bug do conector, credencial ausente ou banco: a falha fica registrada e a política de
        # falhas reagenda, em vez de a Sincronização ficar presa em `running`.
        logger.exception("conector %s: Sincronização falhou", connector["id"])
        result = SyncResult(
            "failed",
            0,
            connector["checkpoint"],
            0,
            "transient",
            "Erro inesperado na Sincronização.",
        )
    await finish(engine, connector, sync_id, result)
    return result.status


async def execute(
    engine: AsyncEngine,
    registry: Mapping[str, type[Connector]],
    policy: RetryPolicy,
    connector: Mapping[str, Any],
    sync_id: str,
) -> SyncResult:
    implementation = registry.get(connector["provider"])
    if implementation is None:
        result = SyncResult(
            "failed",
            0,
            connector["checkpoint"],
            0,
            "invalid",
            "Provedor sem conector neste ambiente.",
        )
    else:
        instance = implementation()
        errors = instance.validate_config(connector["config"])
        if errors:
            result = SyncResult(
                "failed",
                0,
                connector["checkpoint"],
                0,
                "invalid",
                "Configuração inválida: " + ", ".join(sorted(errors)),
            )
        else:
            secret = await secret_of(engine, connector["id"])

            async def sink(batch: Batch) -> None:
                await store_batch(engine, connector, sync_id, batch)

            result = await run_sync(
                instance, secret, connector["config"], connector["checkpoint"], sink, policy
            )
    return result
