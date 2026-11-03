"""Rotas da Trilha de auditoria (ticket #28): Owner e Admin com MFA. Busca e exportação pelo
corpo (POST): o termo pode ser o e-mail de alguém e não vai para a URL nem para os logs."""

import csv
import io
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from aid_api.audit.repo import AuditRepository, get_audit_repository
from aid_api.audit.schemas import AuditPage, AuditSearch
from aid_api.core.auth import Claims, require_manager
from aid_api.core.permissions import READ_AUDIT
from aid_api.core.rate_limit import rate_limit

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"], dependencies=[Depends(rate_limit)])

Manager = Annotated[Claims, Depends(require_manager(*READ_AUDIT))]
Repository = Annotated[AuditRepository, Depends(get_audit_repository)]
COLUMNS = [
    "occurred_at",
    "actor_type",
    "actor",
    "action",
    "resource_type",
    "resource_id",
    "before",
    "after",
    "ip",
]


def cell(value: str) -> str:
    """Planilha não executa o conteúdo: valor que começa como fórmula ganha um apóstrofo."""
    return f"'{value}" if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@router.post("/search", response_model=AuditPage)
async def search_audit(query: AuditSearch, claims: Manager, repository: Repository) -> AuditPage:
    return await repository.search(claims, query)


@router.post("/export", response_class=StreamingResponse)
async def export_audit(
    query: AuditSearch, claims: Manager, repository: Repository
) -> StreamingResponse:
    """CSV de até 50 mil registros, gerado enquanto é enviado."""
    await repository.start_export(claims, query)

    async def rows() -> AsyncIterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(COLUMNS)
        async for item in repository.export(claims, query):
            writer.writerow(
                [
                    cell(value)
                    for value in (
                        item.occurred_at.isoformat(),
                        item.actor_type,
                        item.actor_label or item.actor_id or "",
                        item.action,
                        item.resource_type or "",
                        item.resource_id or "",
                        json.dumps(item.before, ensure_ascii=False) if item.before else "",
                        json.dumps(item.after, ensure_ascii=False) if item.after else "",
                        item.ip or "",
                    )
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate()
        yield buffer.getvalue()

    return StreamingResponse(
        rows(),
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": 'attachment; filename="auditoria.csv"'},
    )
