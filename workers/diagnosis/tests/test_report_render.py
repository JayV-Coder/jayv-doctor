"""Conteúdo do Relatório técnico (ticket #32), sem banco: o que o template diz em cada caso."""

import hashlib
from datetime import UTC, datetime
from typing import Any

from aid_diagnosis_worker.report_render import ReportData, render

AT = datetime(2026, 10, 29, 18, 10, tzinfo=UTC)


DIAGNOSIS: dict[str, Any] = {
    "version": 1,
    "status": "published",
    "mode": "hybrid",
    "classification": "TIMEOUT",
    "probable_cause": "Tempo limite excedido na chamada ao SAP.",
    "confidence": 0.68,
    "responsible_system": None,
    "requires_human_review": True,
    "verification_notes": [],
    "provider": "anthropic",
    "model": "claude-opus-5-5",
    "ruleset_version": "2026.10.1",
}
EVIDENCE: dict[str, Any] = {
    "rank": 1,
    "kind": "event",
    "reference": "0192e1c4-0000-7000-8000-000000000101",
    "label": "gateway",
    "finding": "HTTP 504 após 30 s",
    "excerpt": None,
}


def data(**changes: Any) -> ReportData:
    base: dict[str, Any] = {
        "organization": "Acme Consultoria",
        "incident": {
            "number": 142,
            "title": "Timeout na criação de pedidos SAP",
            "category": "TIMEOUT",
            "severity": "high",
            "status": "open",
            "integration": "Pedidos Salesforce → SAP",
            "environment": "prd",
            "first_seen_at": AT,
            "last_seen_at": AT,
            "execution_count": 37,
            "rule_code": "INT-003",
            "rule_version": "2026.10.1",
        },
        "diagnosis": DIAGNOSIS,
        "hypotheses": [{"rank": 1, "statement": "Gateway lento.", "confidence": 0.68}],
        "evidence": [EVIDENCE],
        "recommendations": [
            {"rank": 1, "text": "Consultar o processamento no SAP.", "kind": "investigate"}
        ],
        "reviews": [],
        "timeline": None,
        "generated_at": AT,
    }
    base.update(changes)
    return ReportData(**base)


def test_markdown_tem_as_secoes_do_template_e_a_confianca_heuristica() -> None:
    report = render(data(), "md")
    body = report.content.decode()
    assert body.startswith("# Relatório técnico · Acme Consultoria")
    assert "INC-0142 · Timeout na criação de pedidos SAP" in body
    assert "Diagnóstico v1 · regras 2026.10.1 · modelo claude-opus-5-5" in body
    for heading in ("## Resumo", "## Causa provável", "## Evidências", "## Recomendações"):
        assert heading in body
    assert "confiança heurística 0,68" in body
    assert "0192e1c4-0000-7000-8000-000000000101" in body
    assert "## Revisão humana\n\nPendente." in body
    assert "## Timeline" not in body


def test_rodape_traz_a_data_e_o_hash_do_conteudo() -> None:
    report = render(data(), "md")
    body, footer = report.content.decode().rsplit("\n---\n", 1)
    assert hashlib.sha256((body + "\n").encode()).hexdigest() == report.sha256
    assert report.sha256 in footer
    assert "29/10/2026 15:10" in footer


def test_inconclusivo_diz_evidencias_insuficientes_e_lista_o_que_coletar() -> None:
    inconclusive = data(
        diagnosis={**DIAGNOSIS, "status": "inconclusive", "probable_cause": None},
        recommendations=[
            {"rank": 1, "text": "Coletar o log do gateway.", "kind": "investigate"},
            {"rank": 2, "text": "Exportar o IDoc.", "kind": "investigate"},
        ],
    )
    body = render(inconclusive, "md").content.decode()
    assert "## Evidências insuficientes" in body
    assert "## Causa provável" not in body
    assert "O que coletar:\n\n1. Coletar o log do gateway.\n2. Exportar o IDoc." in body


def test_sem_diagnostico_concluido() -> None:
    body = render(data(diagnosis=None, hypotheses=[], evidence=[], recommendations=[]), "md")
    assert "Sem Diagnóstico concluído para este Incidente." in body.content.decode()


def test_revisao_timeline_e_trecho_sanitizado() -> None:
    report = data(
        reviews=[
            {"verdict": "corrected", "reviewer": "Ana", "comment": "Era o proxy.", "created_at": AT}
        ],
        timeline=[
            {"timestamp": AT, "operation": "BAPI", "severity": "ERROR", "summary": "HTTP 504"}
        ],
        evidence=[
            {
                **EVIDENCE,
                "excerpt": '{"message": "falhou para ana@acme.com.br", "cpf": "123.456.789-09"}',
            }
        ],
    )
    body = render(report, "md").content.decode()
    assert "Corrigido por Ana em 29/10/2026 15:10: Era o proxy." in body
    assert "## Timeline" in body
    assert "15:10:00 · BAPI · ERROR · HTTP 504" in body
    assert "ana@acme.com.br" not in body
    assert "123.456.789-09" not in body


def test_referencia_de_negocio_nunca_sai_em_claro() -> None:
    report = data(evidence=[{**EVIDENCE, "finding": "pedido hmac:" + "f" * 64 + " falhou"}])
    body = render(report, "md").content.decode()
    assert "hmac:" + "f" * 64 not in body


def test_pdf_com_fonte_que_aceita_portugues() -> None:
    report = render(data(), "pdf")
    assert report.content.startswith(b"%PDF")
    assert report.content_type == "application/pdf"
    assert report.sha256 == render(data(), "md").sha256
