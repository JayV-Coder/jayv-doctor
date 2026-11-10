"""Roda, como o worker de diagnóstico, os Diagnósticos na fila da Organização do E2E (ticket #25),
com o FakeProvider no lugar do LLM. `viewer` rebaixa os membros a Viewer. Roda com
`uv run python` na raiz do repositório.

Uso: seed_diagnosis.py <nome da Organização> [viewer]
"""

import asyncio
import json
import os
import sys

from aid_diagnosis_engine.llm.fake import FakeProvider
from aid_diagnosis_worker.diagnose import diagnose
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

DB = os.environ.get("E2E_DB_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres")
# O modelo "não acha" Evidência: o híbrido sai inconclusivo.
INCONCLUSIVE = json.dumps(
    {
        "classification": "UPSTREAM_TIMEOUT",
        "status": "INCONCLUSIVE",
        "probable_cause": "Sem dados do SAP no horário da falha.",
        "confidence": 0.3,
        "responsible_system": "indeterminado",
        "evidence": [],
        "hypotheses": [{"statement": "Lentidão do SAP no horário de pico.", "confidence": 0.3}],
        "recommendations": [
            {"text": "Colete os logs do SAP do horário da falha.", "kind": "investigate"}
        ],
        "requires_human_review": True,
    }
)


async def main(organization: str, viewer: bool) -> None:
    engine = create_async_engine(DB, poolclass=NullPool)
    async with engine.begin() as connection:
        tenant = await connection.scalar(
            text("select id::text from public.organizations where name = :n"), {"n": organization}
        )
        if viewer:
            await connection.execute(
                text(
                    "update doctor.memberships set role = 'viewer'"
                    " where tenant_id = cast(:t as uuid)"
                ),
                {"t": tenant},
            )
            await engine.dispose()
            return
        queued = (
            await connection.execute(
                text(
                    "select id::text from doctor.diagnoses where tenant_id = cast(:t as uuid)"
                    " and status = 'queued' order by version"
                ),
                {"t": tenant},
            )
        ).scalars()
        targets = list(queued)
    for diagnosis in targets:
        provider = FakeProvider([INCONCLUSIVE])

        def scripted(_: str, _project: str | None, chosen: FakeProvider = provider) -> FakeProvider:
            return chosen

        await diagnose(engine, {"diagnosis_id": diagnosis}, scripted)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], len(sys.argv) > 2 and sys.argv[2] == "viewer"))
