"""Comprova a exclusão total de uma Organização (ticket #29): nenhuma tabela do schema doctor
(fora o comprovante), nenhum objeto dos buckets do Doctor e nenhum segredo de Conector órfão no
Vault guarda o tenant_id. Sai com código 1 e a lista do que sobrou, se houver.

Uso: SUPABASE_DB_URL=... uv run python scripts/verify_tenant_deleted.py <tenant_id>
"""

import asyncio
import os
import sys
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def leftovers(url: str, tenant: str) -> list[str]:
    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+asyncpg://", 1), poolclass=NullPool
    )
    found: list[str] = []
    try:
        async with engine.begin() as connection:
            tables = (
                await connection.execute(
                    text(
                        "select c.relname from pg_class c"
                        " where c.relnamespace = 'doctor'::regnamespace"
                        " and c.relkind in ('r', 'p') and not c.relispartition"
                        " and c.relname <> 'deletion_receipts' and exists (select 1"
                        " from pg_attribute a where a.attrelid = c.oid and a.attname = 'tenant_id')"
                        " order by 1"
                    )
                )
            ).scalars()
            for table in list(tables):
                count = await connection.scalar(
                    text(f"select count(*) from doctor.{table} where tenant_id = cast(:t as uuid)"),
                    {"t": tenant},
                )
                if count:
                    found.append(f"doctor.{table}: {count}")
            if await connection.scalar(
                text("select count(*) from doctor.tenants where id = cast(:t as uuid)"),
                {"t": tenant},
            ):
                found.append("doctor.tenants: 1")
            objects = await connection.scalar(
                text(
                    "select count(*) from storage.objects where bucket_id like 'doctor-%'"
                    " and name like :prefix"
                ),
                {"prefix": f"{tenant}/%"},
            )
            if objects:
                found.append(f"storage.objects: {objects}")
            # Conectores e canais da Organização ficam no comprovante; o segredo leva o id no nome.
            secrets = await connection.scalar(
                text(
                    "select count(*) from vault.secrets s where s.name in (select"
                    " 'doctor/connector/' || jsonb_array_elements_text(r.removed -> 'connectors')"
                    " from doctor.deletion_receipts r where r.tenant_id = cast(:t as uuid)"
                    " union all select 'doctor/channel/'"
                    " || jsonb_array_elements_text(coalesce(r.removed -> 'notification_channels',"
                    " '[]')) from doctor.deletion_receipts r where r.tenant_id = cast(:t as uuid))"
                ),
                {"t": tenant},
            )
            if secrets:
                found.append(f"vault.secrets: {secrets}")
    finally:
        await engine.dispose()
    return found


def main() -> None:
    tenant = str(UUID(sys.argv[1]))
    found = asyncio.run(leftovers(os.environ["SUPABASE_DB_URL"], tenant))
    for line in found:
        print(line)
    print("OK: nada da Organização ficou." if not found else "FALHOU: ainda há dados.")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
