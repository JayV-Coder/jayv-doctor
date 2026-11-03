import io
import zipfile

import pytest
from aid_knowledge.extract import DOCX, PDF, ExtractionError, extract_text


def pdf(text: str) -> bytes:
    """PDF mínimo de uma página com texto (Helvetica), montado à mão."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return out.getvalue()


def docx(paragraphs: list[tuple[str | None, str]]) -> bytes:
    body = "".join(
        "<w:p>"
        + (f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else "")
        + f"<w:r><w:t>{text}</w:t></w:r></w:p>"
        for style, text in paragraphs
    )
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return out.getvalue()


def test_pdf_com_texto() -> None:
    assert "Runbook do VL10" in extract_text(pdf("Runbook do VL10"), PDF)


def test_docx_com_titulos_vira_markdown() -> None:
    text = extract_text(docx([("Heading1", "Pedidos"), (None, "Reinicie o job.")]), DOCX)
    assert text == "# Pedidos\n\nReinicie o job."


def test_markdown_e_texto() -> None:
    assert extract_text("# Título\n\ncorpo".encode(), "text/markdown").startswith("# Título")


@pytest.mark.parametrize(
    ("data", "kind"),
    [(b"nao e pdf", PDF), (b"nao e zip", DOCX), (b"   ", "text/plain"), (b"x", "image/png")],
)
def test_arquivo_invalido_ou_vazio_falha_sem_ecoar(data: bytes, kind: str) -> None:
    with pytest.raises(ExtractionError) as raised:
        extract_text(data, kind)
    assert "nao e" not in str(raised.value)
