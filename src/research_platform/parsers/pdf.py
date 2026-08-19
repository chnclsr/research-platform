from __future__ import annotations

import io

from pypdf import PdfReader

from .base import DocumentParser, ParsedDocument


class PyMuPdfParser(DocumentParser):
    """
    Fast page-oriented PDF text extraction using PyMuPDF (fitz).

    PyMuPDF sorts text blocks into human reading order (sort=True), which keeps
    two-column academic papers from interleaving lines between columns.
    Each page becomes a `# Page N` heading for passage locators.
    """

    id = "pymupdf_fast"
    document_types = ("pdf",)
    capabilities = ("text", "pages")
    priority = 10

    def available(self) -> tuple[bool, str]:
        try:
            import fitz  # noqa: F401
            return True, "PyMuPDF"
        except Exception as exc:
            return False, f"PyMuPDF unavailable: {exc}"

    def can_parse(self, document_type: str, content_type: str, content: bytes) -> bool:
        if document_type not in self.document_types:
            return False
        avail, _ = self.available()
        return avail

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        pages = self._extract_with_fitz(content)
        if pages is None:
            # If PyMuPDF extraction failed on damaged bytes, return empty text
            return ParsedDocument(
                text="",
                document_type="pdf",
                parser_id=self.id,
                page_count=0,
            )
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
                    # sort=True orders blocks top-to-bottom within a column
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


class PyPdfParser(DocumentParser):
    """
    Pure-Python PDF text extraction using pypdf.

    Always available as a fallback when PyMuPDF is not installed or when
    specifically requested by override. Emits the same `# Page N` headings.
    """

    id = "pypdf"
    document_types = ("pdf",)
    capabilities = ("text", "pages")
    priority = 0

    def available(self) -> tuple[bool, str]:
        return True, "pypdf"

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        pages = self._extract_with_pypdf(content)
        return ParsedDocument(
            text="\n\n".join(pages),
            document_type="pdf",
            parser_id=self.id,
            page_count=len(pages),
        )

    def _extract_with_pypdf(self, content: bytes) -> list[str]:
        try:
            reader = PdfReader(io.BytesIO(content))
            page_objects = list(reader.pages)
        except Exception:
            return []
        pages = []
        for index, page in enumerate(page_objects, start=1):
            try:
                extracted = page.extract_text() or ""
            except Exception:
                extracted = ""
            pages.append(f"# Page {index}\n\n{extracted.strip()}")
        return pages


# Alias for backwards compatibility
PdfParser = PyMuPdfParser
