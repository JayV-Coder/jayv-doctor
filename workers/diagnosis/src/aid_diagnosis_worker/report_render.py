"""Template do Relatório técnico (ticket #32). As mesmas seções viram Markdown e, pelo HTML, PDF
(WeasyPrint). O hash do rodapé é o do corpo em Markdown, igual nos dois formatos.

Todo texto passa de novo pelo sanitizador e perde as Referências de negócio (`hmac:…`): o que vem
do banco já foi sanitizado na ingestão, e o relatório sai da plataforma."""

import hashlib
import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from aid_security.sanitizer import Sanitizer

Format = Literal["pdf", "md"]
ZONE = ZoneInfo("America/Sao_Paulo")
REFERENCE = re.compile(r"hmac:[0-9a-f]{64}")
SANITIZER = Sanitizer()

SEVERITY = {"low": "baixa", "medium": "média", "high": "alta", "critical": "crítica"}
SYSTEM = {"sap": "SAP", "salesforce": "Salesforce", "gcp": "GCP", "other": "outro"}
MODE = {"hybrid": "Regras + IA", "rules_only": "só Regras"}
VERDICT = {"accepted": "Aceito", "corrected": "Corrigido", "rejected": "Rejeitado"}
EVIDENCE_KIND = {
    "event": "Evento",
    "raw_log": "Log bruto",
    "chunk": "Base de conhecimento",
    "global_chunk": "Base global",
    "rule_match": "Regra",
    "enrichment": "Consulta ao destino",
}


@dataclass(frozen=True)
class ReportData:
    organization: str
    incident: Mapping[str, Any]
    diagnosis: Mapping[str, Any] | None
    hypotheses: Sequence[Mapping[str, Any]]
    evidence: Sequence[Mapping[str, Any]]
    recommendations: Sequence[Mapping[str, Any]]
    reviews: Sequence[Mapping[str, Any]]
    # `None`: o pedido não incluiu a timeline. Os Eventos mais recentes, até o limite do worker.
    timeline: Sequence[Mapping[str, Any]] | None
    generated_at: datetime
    # Quantos Eventos o Incidente tem, para avisar quando a timeline foi cortada.
    timeline_total: int | None = None


@dataclass(frozen=True)
class Section:
    title: str
    paragraphs: Sequence[str] = ()
    items: Sequence[str] = ()
    ordered: bool = False
    # Trechos de Evento (sanitizados), em bloco de código.
    code: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class Rendered:
    content: bytes
    content_type: str
    # Do arquivo entregue (confere com `sha256sum`); é o que a linha e a trilha guardam.
    sha256: str
    # Do texto (corpo em Markdown), o que sai no rodapé: igual no PDF e no `.md`.
    body_sha256: str


def clean(value: Any) -> str:
    text = REFERENCE.sub("[referência]", str(value))
    sanitized, _ = SANITIZER.sanitize(text)
    return str(sanitized)


# Texto vindo de log e de Usuário não pode virar sintaxe no `.md` (seção falsa, imagem, link).
MARKDOWN = re.compile(r"([\\`*_\[\]<>#!|~])")


def md(text: str) -> str:
    return MARKDOWN.sub(r"\\\1", " ".join(text.split()))


def fence(text: str) -> list[str]:
    """Bloco de código com cerca maior que qualquer sequência de crases do trecho."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    mark = "`" * max(3, longest + 1)
    return [mark, text, mark]


def when(moment: datetime, seconds: bool = False) -> str:
    return moment.astimezone(ZONE).strftime("%d/%m/%Y %H:%M:%S" if seconds else "%d/%m/%Y %H:%M")


def decimal(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def code(number: int | None) -> str:
    return f"INC-{(number or 0):04d}"


def header(data: ReportData) -> tuple[str, str]:
    incident, diagnosis = data.incident, data.diagnosis
    title = f"{code(incident['number'])} · {clean(incident['title'])}"
    parts = [when(incident["last_seen_at"])]
    if diagnosis:
        parts.append(f"Diagnóstico v{diagnosis['version']}")
        parts.append(f"regras {diagnosis.get('ruleset_version') or incident['rule_version']}")
        parts.append(f"modelo {diagnosis.get('model') or 'nenhum (só Regras)'}")
    else:
        parts.append(f"regras {incident['rule_version']}")
    return title, " · ".join(parts)


def summary(data: ReportData) -> Section:
    incident = data.incident
    paragraphs = [
        f'{incident["execution_count"]} Execuções de "{clean(incident["integration"])}"'
        f" ({clean(incident['environment'])}) entre {when(incident['first_seen_at'])} e"
        f" {when(incident['last_seen_at'])}. Categoria {clean(incident['category'])},"
        f" severidade {SEVERITY.get(incident['severity'], incident['severity'])},"
        f" Regra {incident['rule_code']} ({incident['rule_version']})."
    ]
    if data.diagnosis:
        paragraphs.append(f"Modo do Diagnóstico: {MODE.get(data.diagnosis['mode'], '')}.")
    return Section("Resumo", paragraphs)


def cause(data: ReportData) -> list[Section]:
    diagnosis = data.diagnosis
    if diagnosis is None:
        return [Section("Causa provável", ["Sem Diagnóstico concluído para este Incidente."])]
    notes = [clean(note) for note in diagnosis.get("verification_notes") or []]
    if diagnosis["status"] == "inconclusive":
        collect = [clean(item["text"]) for item in data.recommendations]
        return [
            Section(
                "Evidências insuficientes",
                [
                    "O Diagnóstico não afirma uma Causa provável: as Evidências não bastam.",
                    *notes,
                    *(["O que coletar:"] if collect else []),
                ],
                collect,
                ordered=True,
            )
        ]
    confidence = diagnosis.get("confidence")
    title = "Causa provável"
    if confidence is not None:
        title += f" · confiança heurística {decimal(float(confidence))}"
    system = SYSTEM.get(diagnosis.get("responsible_system") or "", "indeterminado")
    paragraphs = [
        clean(diagnosis.get("probable_cause") or "Não informada."),
        f"Sistema responsável: {system}.",
        *notes,
    ]
    hypotheses = [
        f"{clean(item['statement'])}"
        + (
            f" (confiança heurística {decimal(float(item['confidence']))})"
            if item.get("confidence") is not None
            else ""
        )
        for item in data.hypotheses
    ]
    sections = [Section(title, paragraphs)]
    if len(hypotheses) > 1:
        sections.append(Section("Hipóteses", items=hypotheses, ordered=True))
    return sections


def evidence(data: ReportData) -> Section:
    items, excerpts = [], []
    for item in data.evidence:
        kind = EVIDENCE_KIND.get(item["kind"], item["kind"])
        reference = item.get("reference") or "registro removido pela retenção"
        label, finding = clean(item["label"]), clean(item["finding"])
        items.append(f"[E{item['rank']}] {kind} {reference} · {label}: {finding}")
        if item.get("excerpt"):
            excerpts.append(f"[E{item['rank']}] {clean(item['excerpt'])}")
    if not items:
        return Section("Evidências", ["Nenhuma Evidência registrada."])
    return Section("Evidências", items=items, code=excerpts)


def recommendations(data: ReportData) -> Section | None:
    if data.diagnosis is None or data.diagnosis["status"] == "inconclusive":
        return None
    items = [clean(item["text"]) for item in data.recommendations]
    paragraphs = [] if items else ["Nenhuma Recomendação."]
    return Section("Recomendações", paragraphs, items, ordered=True)


def review(data: ReportData) -> Section | None:
    if data.diagnosis is None:
        return None
    if not data.reviews:
        return Section("Revisão humana", ["Pendente."])
    items = []
    for item in data.reviews:
        line = f"{VERDICT.get(item['verdict'], item['verdict'])} por {clean(item['reviewer'])}"
        line += f" em {when(item['created_at'])}"
        if item.get("comment"):
            line += f": {clean(item['comment'])}"
        items.append(line)
    return Section("Revisão humana", items=items)


def timeline(data: ReportData) -> Section | None:
    if data.timeline is None:
        return None
    items = [
        f"{when(item['timestamp'], seconds=True)} · {clean(item['operation'])}"
        f" · {item['severity']}" + (f" · {clean(item['summary'])}" if item.get("summary") else "")
        for item in data.timeline
    ]
    paragraphs = [] if items else ["Sem Eventos."]
    total = data.timeline_total or len(items)
    if total > len(items):
        paragraphs.append(f"Os {len(items)} Eventos mais recentes, de {total}.")
    return Section("Timeline", paragraphs, items)


def sections(data: ReportData) -> list[Section]:
    found = [
        summary(data),
        *cause(data),
        evidence(data),
        recommendations(data),
        review(data),
        timeline(data),
    ]
    return [section for section in found if section is not None]


def markdown_body(data: ReportData) -> str:
    title, subtitle = header(data)
    lines = [
        f"# Relatório técnico · {md(clean(data.organization))}",
        "",
        f"**{md(title)}**",
        "",
        md(subtitle),
    ]
    for section in sections(data):
        lines += ["", f"## {md(section.title)}"]
        for paragraph in section.paragraphs:
            lines += ["", md(paragraph)]
        if section.items:
            lines.append("")
            for index, item in enumerate(section.items, 1):
                lines.append(f"{index}. {md(item)}" if section.ordered else f"- {md(item)}")
        for excerpt in section.code:
            lines += ["", *fence(excerpt)]
    # Termina em linha em branco: o `---` do rodapé não vira título do parágrafo anterior.
    return "\n".join(lines) + "\n\n"


def footer(data: ReportData, digest: str) -> str:
    return f"Gerado em {when(data.generated_at)} (horário de Brasília) · sha256 do texto {digest}"


STYLE = " ".join(
    (
        "@page { size: A4; margin: 18mm 16mm; }",
        'body { font-family: "DejaVu Sans Mono", monospace; font-size: 9.5pt; color: #161616;',
        "line-height: 1.45; }",
        ".label { color: #63635f; text-transform: uppercase; letter-spacing: .04em;",
        "font-size: 8pt; }",
        "h1 { font-size: 13pt; margin: 4pt 0; }",
        ".mu { color: #63635f; }",
        "h2 { font-size: 10.5pt; margin: 14pt 0 4pt; }",
        # O prompt do kit (U+276F), escrito como escape do CSS.
        'h2::before { content: "\\276F  "; }',
        "pre { background: #eaeae5; padding: 6pt; white-space: pre-wrap; word-break: break-all;",
        "font-size: 8pt; }",
        "footer { margin-top: 18pt; border-top: 1px solid #d8d8d2; padding-top: 6pt;",
        "color: #63635f; font-size: 7.5pt; word-break: break-all; }",
    )
)


def html_document(data: ReportData, digest: str) -> str:
    def esc(value: str) -> str:
        return html.escape(value, quote=False)

    title, subtitle = header(data)
    parts = [
        f'<span class="label">Relatório técnico · {esc(clean(data.organization))}</span>',
        f"<h1>{esc(title)}</h1>",
        f'<span class="mu">{esc(subtitle)}</span>',
    ]
    for section in sections(data):
        parts.append(f"<h2>{esc(section.title)}</h2>")
        parts += [f"<p>{esc(paragraph)}</p>" for paragraph in section.paragraphs]
        if section.items:
            tag = "ol" if section.ordered else "ul"
            items = "".join(f"<li>{esc(item)}</li>" for item in section.items)
            parts.append(f"<{tag}>{items}</{tag}>")
        parts += [f"<pre>{esc(excerpt)}</pre>" for excerpt in section.code]
    parts.append(f"<footer>{esc(footer(data, digest))}</footer>")
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        f"<style>{STYLE}</style></head><body>{''.join(parts)}</body></html>"
    )


def render(data: ReportData, format: Format) -> Rendered:
    body = markdown_body(data)
    digest = hashlib.sha256(body.encode()).hexdigest()
    if format == "md":
        content = f"{body}---\n{footer(data, digest)}\n".encode()
        return Rendered(content, "text/markdown", hashlib.sha256(content).hexdigest(), digest)
    from weasyprint import HTML  # type: ignore[import-untyped]  # pesado: só no PDF

    pdf = bytes(HTML(string=html_document(data, digest)).write_pdf() or b"")
    return Rendered(pdf, "application/pdf", hashlib.sha256(pdf).hexdigest(), digest)
