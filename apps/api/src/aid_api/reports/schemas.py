"""Contratos do Relatório técnico (ticket #32)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ReportFormat = Literal["pdf", "md"]
ReportStatus = Literal["queued", "running", "ready", "failed"]


class ReportRequest(BaseModel):
    format: ReportFormat = "pdf"
    include_timeline: bool = False
    include_event_excerpts: bool = False


class ReportQueued(BaseModel):
    report_id: str
    status: ReportStatus


class ReportShare(BaseModel):
    id: str
    expires_at: datetime
    revoked_at: datetime | None
    access_count: int
    last_accessed_at: datetime | None
    created_at: datetime


class ReportSummary(BaseModel):
    id: str
    incident_id: str
    diagnosis_id: str | None
    diagnosis_version: int | None
    format: ReportFormat
    include_timeline: bool
    include_event_excerpts: bool
    status: ReportStatus
    size_bytes: int | None
    content_sha256: str | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None


class Report(ReportSummary):
    # Só quando pronto: URL assinada de 5 min.
    download_url: str | None
    expires_in: int | None
    # Os links, para quem compartilha (Analyst ou acima); vazio para o Viewer.
    shares: list[ReportShare]


class ReportShareCreated(BaseModel):
    id: str
    # O token só aparece aqui, no fragmento (fora dos logs de acesso).
    url: str
    expires_at: datetime


class SharedReportRequest(BaseModel):
    token: str = Field(min_length=32, max_length=128)
