"""Texto de PDF, DOCX, Markdown e TXT (até 20 MB). Só o texto: imagens e macros ficam de fora."""

import io
import re
import zipfile
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT = ("text/markdown", "text/plain")
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# Um DOCX descompactado gigante é sinal de bomba de zip.
MAX_UNZIPPED = 100 * 1024 * 1024


class ExtractionError(ValueError):
    """Arquivo ilegível ou fora do formato declarado; a mensagem não traz o conteúdo."""


def _docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_UNZIPPED:
                raise ExtractionError("DOCX grande demais depois de descompactado.")
            root = ElementTree.fromstring(archive.read(info))  # noqa: S314 - XML do próprio DOCX, sem DTD
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ExtractionError("O arquivo não é um DOCX válido.") from exc
    paragraphs = []
    for paragraph in root.iter(f"{WORD}p"):
        style = paragraph.find(f"{WORD}pPr/{WORD}pStyle")
        text = "".join(node.text or "" for node in paragraph.iter(f"{WORD}t")).strip()
        if not text:
            continue
        name = (style.get(f"{WORD}val") if style is not None else "") or ""
        level = re.match(r"(?:Heading|Ttulo|Titulo)(\d)", name)
        paragraphs.append(f"{'#' * int(level.group(1))} {text}" if level else text)
    return "\n\n".join(paragraphs)


def _pdf(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError) as exc:
        raise ExtractionError("O arquivo não é um PDF válido.") from exc
    return "\n\n".join(page.strip() for page in pages if page.strip())


def extract_text(data: bytes, content_type: str) -> str:
    if content_type == PDF:
        text = _pdf(data)
    elif content_type == DOCX:
        text = _docx(data)
    elif content_type in TEXT:
        text = data.decode("utf-8", errors="replace")
    else:
        raise ExtractionError("Formato não suportado.")
    if not text.strip():
        raise ExtractionError("Nenhum texto encontrado no arquivo (PDF escaneado sem OCR?).")
    return text
