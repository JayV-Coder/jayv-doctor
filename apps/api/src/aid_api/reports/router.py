"""Rotas do Relatório técnico (ticket #32). Gerar é assíncrono (`202`, o worker de diagnóstico
gera o arquivo); todo Papel baixa por URL assinada de 5 min; Analyst ou acima compartilha um link
de 7 dias, revogável e auditado. Quem tem o link abre sem sessão, pela API (ADR-0014)."""

import hashlib
import json
import os
import secrets
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Response, status

from aid_api.core.auth import Claims, get_bearer_token, require_role
from aid_api.core.errors import ApiError
from aid_api.core.idempotency import Idempotent, IdempotentRoute
from aid_api.core.permissions import OPERATE, VIEW
from aid_api.core.rate_limit import rate_limit
from aid_api.core.storage import Storage, get_storage
from aid_api.reports.repo import ReportRepository, get_report_repository
from aid_api.reports.schemas import (
    Report,
    ReportQueued,
    ReportRequest,
    ReportShareCreated,
    ReportSummary,
    SharedReportRequest,
)

BUCKET = "doctor-reports"
DOWNLOAD_SECONDS = 300
SHARE_SECONDS = 7 * 24 * 3600
MEDIA = {"pdf": "application/pdf", "md": "text/markdown; charset=utf-8"}

router = APIRouter(
    prefix="/api/v1",
    tags=["reports"],
    route_class=IdempotentRoute,
    dependencies=[Depends(rate_limit)],
)
# Sem sessão: o limite por IP é do Cloud Armor.
shared = APIRouter(prefix="/api/v1", tags=["reports"])

Viewer = Annotated[Claims, Depends(require_role(*VIEW))]
Operator = Annotated[Claims, Depends(require_role(*OPERATE))]
Repository = Annotated[ReportRepository, Depends(get_report_repository)]
StorageDep = Annotated[Storage, Depends(get_storage)]
Token = Annotated[str, Depends(get_bearer_token)]


def processing_key(claims: Claims, incident: str, body: ReportRequest, key: str) -> str:
    material = json.dumps([claims.sub, incident, body.model_dump(), key], separators=(",", ":"))
    return f"req:{hashlib.sha256(material.encode()).hexdigest()}"


@router.post(
    "/incidents/{incident}/reports",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReportQueued,
)
async def request_report(
    incident: UUID,
    body: ReportRequest,
    claims: Operator,
    repository: Repository,
    _: Idempotent,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=255)] = None,
) -> ReportQueued:
    return await repository.request(
        claims,
        str(incident),
        body,
        processing_key(claims, str(incident), body, idempotency_key or str(uuid4())),
    )


@router.get("/incidents/{incident}/reports", response_model=list[ReportSummary])
async def list_reports(
    incident: UUID, claims: Viewer, repository: Repository
) -> list[ReportSummary]:
    return await repository.for_incident(claims, str(incident))


@router.get("/reports/{target}", response_model=Report)
async def get_report(
    target: UUID, claims: Viewer, token: Token, repository: Repository, storage: StorageDep
) -> Report:
    async def sign(path: str) -> str:
        return await storage.sign_download(token, path, DOWNLOAD_SECONDS, BUCKET)

    summary, url, shares = await repository.detail(claims, str(target), sign)
    return Report(
        **summary.model_dump(),
        download_url=url,
        expires_in=DOWNLOAD_SECONDS if url else None,
        shares=shares,
    )


@router.post(
    "/reports/{target}/shares",
    status_code=status.HTTP_201_CREATED,
    response_model=ReportShareCreated,
)
async def share_report(
    target: UUID, claims: Operator, token: Token, repository: Repository, storage: StorageDep
) -> ReportShareCreated:
    path = await repository.ready_path(claims, str(target))
    # A URL assinada fica no banco e nunca sai da API: quem tem o link recebe o arquivo pelo proxy.
    signed = await storage.sign_download(token, path, SHARE_SECONDS, BUCKET)
    secret = secrets.token_urlsafe(32)
    share_id, expires_at = await repository.share(claims, str(target), secret, signed)
    base = os.environ.get("APP_URL", "http://127.0.0.1:3000").rstrip("/")
    return ReportShareCreated(
        id=share_id, url=f"{base}/compartilhado#{secret}", expires_at=expires_at
    )


@router.delete("/reports/{target}/shares/{share}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(target: UUID, share: UUID, claims: Operator, repository: Repository) -> None:
    await repository.revoke(claims, str(target), str(share))


@shared.post(
    "/shared-reports",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}, "text/markdown": {}}}},
)
async def open_shared_report(
    body: SharedReportRequest, repository: Repository, storage: StorageDep
) -> Response:
    """O token vem no corpo (fora da URL e dos logs). Link inválido, vencido ou revogado: 404."""
    found = await repository.open_shared(body.token)
    content = await storage.fetch(found.download_url) if found else None
    if found is None or content is None:
        raise ApiError(404, "not_found", "Link inválido, vencido ou revogado.")
    return Response(
        content,
        media_type=MEDIA[found.format],
        headers={
            "content-disposition": f'attachment; filename="{found.filename}"',
            "cache-control": "no-store",
        },
    )
