"""Pipeline contra um Postgres real. Roda só com INTEGRATION_DB_URL, no job de E2E do CI."""

import hashlib
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from aid_ingestion.pipeline import ObjectStore, process_import
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("INTEGRATION_DB_URL")
pytestmark = pytest.mark.skipif(URL is None, reason="sem INTEGRATION_DB_URL")
FIXTURES = Path(__file__).parent / "fixtures"
MASTER = b"chave-mestre-de-teste-com-32-bytes!!"

NDJSON = (
    b'{"timestamp": "2026-11-02T14:05:00Z", "operation": "BAPI_SALESORDER", "level": "E",'
    b' "message": "Timeout", "Authorization": "Bearer 9f8e7d6c5b4a39281706f5e4d3c2b1a0",'
    b' "cliente": "ana.souza@acme.com.br"}\n'
    b'{"timestamp": "2026-11-02T14:05:00Z", "operation": "BAPI_SALESORDER", "level": "E",'
    b' "message": "Timeout", "Authorization": "Bearer 9f8e7d6c5b4a39281706f5e4d3c2b1a0",'
    b' "cliente": "ana.souza@acme.com.br"}\n'
    b'{"operation": "sem data"}\n'
    b"nao-e-json\n"
    b'{"timestamp": "2026-10-15T09:00:00Z", "operation": "BAPI_CUSTOMER", "level": "S"}\n'
)


class MemoryStore(ObjectStore):
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    async def read(self, path: str) -> bytes | None:
        return self.objects.get(path)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert URL is not None
    created = create_async_engine(
        URL.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    yield created
    await created.dispose()


async def scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.begin() as connection:
        return await connection.scalar(text(sql), params)


async def row(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.begin() as connection:
        return (await connection.execute(text(sql), params)).mappings().one()


@pytest_asyncio.fixture
async def tenant(engine: AsyncEngine) -> AsyncIterator[dict[str, str]]:
    ids = {"tenant": str(uuid4()), "integration": str(uuid4())}
    async with engine.begin() as connection:
        await connection.execute(
            text("insert into public.organizations (id, name, slug) values (:t, 'T', :s)"),
            {"t": ids["tenant"], "s": f"t-{ids['tenant'][:30]}"},
        )
        await connection.execute(
            text("insert into doctor.tenants (id) values (:t)"), {"t": ids["tenant"]}
        )
        await connection.execute(
            text(
                "insert into doctor.integrations"
                " (id, tenant_id, name, source_system, target_system, environment)"
                " values (:i, :t, 'Pedidos', 'salesforce', 'sap', 'prd')"
            ),
            {"i": ids["integration"], "t": ids["tenant"]},
        )
    yield ids
    async with engine.begin() as connection:
        for table in ("events", "outbox_messages", "imports", "raw_log_objects", "integrations"):
            await connection.execute(
                text(f"delete from doctor.{table} where tenant_id = :t"),  # noqa: S608
                {"t": ids["tenant"]},
            )
        await connection.execute(
            text("delete from doctor.tenants where id = :t"), {"t": ids["tenant"]}
        )
        await connection.execute(
            text("delete from public.organizations where id = :t"), {"t": ids["tenant"]}
        )


async def uploaded_import(
    engine: AsyncEngine, ids: dict[str, str], data: bytes, file_format: str = "ndjson"
) -> tuple[str, str]:
    import_id, raw_id = str(uuid4()), str(uuid4())
    path = f"{ids['tenant']}/imports/{import_id}/upload.{file_format}"
    sha = hashlib.sha256(data).hexdigest()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into doctor.raw_log_objects"
                " (id, tenant_id, storage_path, sha256, size_bytes, source)"
                " values (:r, :t, :p, :s, :n, 'import')"
            ),
            {"r": raw_id, "t": ids["tenant"], "p": path, "s": sha, "n": len(data)},
        )
        await connection.execute(
            text(
                "insert into doctor.imports (id, tenant_id, integration_id, raw_log_object_id,"
                " filename, size_bytes, sha256, format, status)"
                " values (:i, :t, :g, :r, 'f', :n, :s, :f, 'uploaded')"
            ),
            {
                "i": import_id,
                "t": ids["tenant"],
                "g": ids["integration"],
                "r": raw_id,
                "n": len(data),
                "s": sha,
                "f": file_format,
            },
        )
    return import_id, path


async def run(engine: AsyncEngine, import_id: str, path: str, data: bytes) -> str:
    return await process_import({"import_id": import_id}, engine, MemoryStore({path: data}), MASTER)


@pytest.mark.asyncio
async def test_importacao_vira_eventos_sanitizados_com_rejeicoes_e_contadores(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    import_id, path = await uploaded_import(engine, tenant, NDJSON)
    assert await run(engine, import_id, path, NDJSON) == "done"

    result = await row(
        engine,
        "select status, total_lines, accepted, rejected, duplicates, secrets_removed"
        " from doctor.imports where id = :i",
        i=import_id,
    )
    assert dict(result) == {
        "status": "done",
        "total_lines": 5,
        "accepted": 2,
        "rejected": 2,
        "duplicates": 1,
        "secrets_removed": 4,
    }
    reasons = await scalar(
        engine,
        "select string_agg(line_number || ':' || reason, ' | ' order by line_number)"
        " from doctor.import_rejections where import_id = :i",
        i=import_id,
    )
    assert reasons == "3:linha sem data (timestamp) | 4:JSON inválido"

    stored = await scalar(
        engine,
        "select string_agg(attributes::text || error::text, '')"
        " from doctor.events where tenant_id = :t",
        t=tenant["tenant"],
    )
    assert "ana.souza" not in stored
    assert "9f8e7d6c" not in stored
    assert "[REMOVIDO:email]" in stored
    partitions = await scalar(
        engine,
        "select count(*) from pg_inherits where inhparent = 'doctor.events'::regclass"
        " and inhrelid::regclass::text in ('doctor.events_2026_10', 'doctor.events_2026_11')",
    )
    assert partitions == 2
    outbox = await scalar(
        engine,
        "select count(*) from doctor.outbox_messages where topic = 'correlation.requested'"
        " and payload ->> 'import_id' = :i",
        i=import_id,
    )
    assert outbox == 1


@pytest.mark.asyncio
async def test_reentrega_e_queda_no_meio_nao_duplicam(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    import_id, path = await uploaded_import(engine, tenant, NDJSON)
    assert await run(engine, import_id, path, NDJSON) == "done"
    # Mensagem reentregue depois do commit: nada a fazer.
    assert await run(engine, import_id, path, NDJSON) == "ignored"
    # Worker caiu depois de gravar e antes do ack: a Importação ficou em processing.
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "update doctor.imports set status = 'processing',"
                " processing_started_at = now() - interval '1 hour' where id = :i"
            ),
            {"i": import_id},
        )
    assert await run(engine, import_id, path, NDJSON) == "done"

    events = await scalar(
        engine, "select count(*) from doctor.events where tenant_id = :t", t=tenant["tenant"]
    )
    assert events == 2
    accepted = await scalar(
        engine, "select accepted from doctor.imports where id = :i", i=import_id
    )
    assert accepted == 2
    rejections = await scalar(
        engine, "select count(*) from doctor.import_rejections where import_id = :i", i=import_id
    )
    assert rejections == 2


@pytest.mark.asyncio
async def test_mesmos_eventos_em_outro_arquivo_contam_como_duplicados(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    first, first_path = await uploaded_import(engine, tenant, NDJSON)
    await run(engine, first, first_path, NDJSON)
    again = NDJSON + b"\n"
    second, second_path = await uploaded_import(engine, tenant, again)
    await run(engine, second, second_path, again)
    result = await row(
        engine, "select accepted, duplicates from doctor.imports where id = :i", i=second
    )
    assert dict(result) == {"accepted": 0, "duplicates": 3}


@pytest.mark.asyncio
async def test_arquivo_diferente_do_enviado_falha_sem_gravar(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    import_id, path = await uploaded_import(engine, tenant, NDJSON)
    assert await run(engine, import_id, path, b'{"adulterado": true}\n') == "failed"
    result = await row(
        engine, "select status, error from doctor.imports where id = :i", i=import_id
    )
    assert dict(result) == {"status": "failed", "error": "Arquivo diferente do que foi enviado"}


@pytest.mark.asyncio
async def test_csv_latin1(engine: AsyncEngine, tenant: dict[str, str]) -> None:
    data = (FIXTURES / "bapi-errors-latin1.csv").read_bytes()
    import_id, path = await uploaded_import(engine, tenant, data, "csv")
    assert await run(engine, import_id, path, data) == "done"
    result = await row(
        engine,
        "select severity, error ->> 'message' as message, operation from doctor.events"
        " where raw_log_object_id = (select raw_log_object_id from doctor.imports where id = :i)",
        i=import_id,
    )
    assert dict(result) == {
        "severity": "ERROR",
        "message": "Pedido não encontrado",
        "operation": "BAPI_SALESORDER",
    }


@pytest.mark.asyncio
async def test_data_numerica_que_passa_no_luhn_nao_vira_cartao(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    data = b"ts;data_hora;docnum;mensagem\n1793628300005;x;20261102140500;ok\n"
    data += b";20261102140500;1;ok\n"
    import_id, path = await uploaded_import(engine, tenant, data, "csv")
    assert await run(engine, import_id, path, data) == "done"
    result = await row(
        engine, "select accepted, rejected from doctor.imports where id = :i", i=import_id
    )
    assert dict(result) == {"accepted": 2, "rejected": 0}
    execution = await scalar(
        engine,
        "select string_agg(execution_id, ',' order by execution_id) from doctor.events"
        " where raw_log_object_id = (select raw_log_object_id from doctor.imports where id = :i)",
        i=import_id,
    )
    assert execution == "1,20261102140500"


@pytest.mark.asyncio
async def test_segunda_entrega_durante_o_processamento_espera_a_vez(
    engine: AsyncEngine, tenant: dict[str, str]
) -> None:
    from aid_ingestion.pipeline import BusyError, claim

    import_id, path = await uploaded_import(engine, tenant, NDJSON)
    assert await claim(engine, import_id) is not None
    with pytest.raises(BusyError):
        await run(engine, import_id, path, NDJSON)
    # Prazo vencido (worker morto): a próxima entrega assume.
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "update doctor.imports set processing_started_at = now() - interval '1 hour'"
                " where id = :i"
            ),
            {"i": import_id},
        )
    assert await run(engine, import_id, path, NDJSON) == "done"


@pytest.mark.asyncio
async def test_erro_inesperado_encerra_a_importacao_como_falha(
    engine: AsyncEngine, tenant: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import aid_ingestion.pipeline as pipeline

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("bug")

    monkeypatch.setattr(pipeline, "to_event", broken)
    import_id, path = await uploaded_import(engine, tenant, NDJSON)
    assert await run(engine, import_id, path, NDJSON) == "failed"
    result = await row(
        engine, "select status, error from doctor.imports where id = :i", i=import_id
    )
    assert dict(result) == {
        "status": "failed",
        "error": "Erro inesperado ao processar o arquivo. Importe de novo.",
    }
