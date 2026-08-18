from __future__ import annotations

import io

from pypdf import PdfReader

from .base import DocumentParser, ParsedDocument


class PdfParser(DocumentParser):
    """
    Page-oriented PDF text extraction.

    Each page becomes a `# Page N` heading, which is what lets chunk_document() derive
    `page_number` for passage locators — see the `Page (\\d+)$` match in passages.py.
    Any replacement parser must keep emitting those headings.

    PyMuPDF is preferred because it sorts text blocks into reading order, which keeps the
    two-column layouts common in academic papers from interleaving. pypdf remains the
    fallback so the parser still works if PyMuPDF is unavailable.
    """

    id = "pdf"
    document_types = ("pdf",)
    capabilities = ("text", "pages")
    priority = 0

    def available(self) -> tuple[bool, str]:
        try:
            import fitz  # noqa: F401
        except Exception:
            return True, "PyMuPDF unavailable; falling back to pypdf"
        return True, "PyMuPDF"

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        pages = self._extract_with_fitz(content)
        if pages is None:
            pages = self._extract_with_pypdf(content)
        return ParsedDocument(
            text="\n\n".join(pages),
            document_type="pdf",
            parser_id=self.id,
            page_count=len(pages),
        )

    def _extract_with_fitz(self, content: bytes) -> list[str] | None:
        try:
            import fitz
        except Exception:
            return None
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception:
            return None
        pages: list[str] = []
        try:
            for index, page in enumerate(document, start=1):
                try:
                    # sort=True orders blocks top-to-bottom within a column before moving
                    # to the next one, instead of raw content-stream order.
                    extracted = page.get_text("text", sort=True) or ""
                except Exception:
                    extracted = ""
                pages.append(f"# Page {index}\n\n{extracted.strip()}")
        finally:
            try:
                document.close()
            except Exception:
                pass
        return pages

    def _extract_with_pypdf(self, content: bytes) -> list[str]:
        try:
            reader = PdfReader(io.BytesIO(content))
            page_objects = list(reader.pages)
        except Exception:
            # A truncated or mislabelled download must not abort acquisition; the caller
            # rejects the document on the resulting empty text instead.
            return []
        pages = []
        for index, page in enumerate(page_objects, start=1):
            try:
                extracted = page.extract_text() or ""
            except Exception:
                # One unreadable page should not cost us the rest of the document.
                extracted = ""
            pages.append(f"# Page {index}\n\n{extracted}")
        return pages
