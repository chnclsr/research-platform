"""
Page-routed PDF parsing.

Where PdfParser sends every page through one extractor, this parser inspects each
page first and only spends the expensive engine on pages that need it: a scanned
page, a page holding a table, or a page whose extracted text fails a quality
check. Measured on a 9-document / 261-page corpus, 44% of pages stay on the cheap
path, and the routing decision itself costs 0.65-14.84 ms/page against 1550
ms/page for the heavy engine.

The `# Page N` headings are emitted here for the same reason PdfParser emits them:
chunk_document() derives `page_number` from them (see passages.py). Because pages
can come from different engines, the headings are applied once after the pages are
merged rather than by each engine.
"""

from __future__ import annotations

import os
import re
import tempfile

from .base import DocumentParser, ParsedDocument

try:
    from .smart_router import ROUTER_VERSION, SmartRouterHatti
    from .smart_router.engines import DoclingEngine
    from .smart_router.gate import ESIK_VERSION
    from .smart_router.merge import MergedDocument, birlestir, sayfa_basliklariyla

    _ROUTER_IMPORT_ERROR: str = ""
except Exception as exc:  # pragma: no cover - exercised only when deps are absent
    SmartRouterHatti = None  # type: ignore[assignment]
    ROUTER_VERSION = ESIK_VERSION = ""
    _ROUTER_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


# Levels 1-5 shift down one; level 6 has nowhere to go and is left alone.
_HEADING = re.compile(r"(?m)^(\s{0,3})(#{1,5})(\s+\S)")


def _nest_under_page(markdown: str) -> str:
    """
    Push a page's own headings one level down so `# Page N` stays the only level-1.

    _sections() in passages.py builds a hierarchical section path and drops every
    ancestor at or above the current heading's level, so a level-1 heading inside a
    page evicts `Page N` from the path entirely and every passage after it loses its
    page number -- silently, as page_number=None rather than an error. Demoting the
    page's own headings keeps them nested underneath the page heading instead.
    """
    return _HEADING.sub(r"\1#\2\3", markdown)


class SmartPdfParser(DocumentParser):
    """
    PDF parser that routes individual pages to the engine each one needs.

    Registered alongside PdfParser rather than replacing it: `priority` decides
    which one wins, so dropping the priority (or returning False from available())
    reverts the pipeline to the plain extractor without touching the registry.
    """

    id = "smart_pdf"
    document_types = ("pdf",)
    capabilities = ("text", "pages")
    # ParserRegistry.select() sorts by (-priority, id), so a tie with PdfParser
    # would hand the document to "pdf" on the alphabetical tiebreak.
    priority = 10

    def available(self) -> tuple[bool, str]:
        if SmartRouterHatti is None:
            return False, f"smart_router unavailable ({_ROUTER_IMPORT_ERROR})"
        return True, "smart_router"

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        if SmartRouterHatti is None:
            return ParsedDocument(document_type="pdf", parser_id=self.id)

        path = self._spill_to_disk(content)
        if path is None:
            return ParsedDocument(document_type="pdf", parser_id=self.id)
        try:
            decision = SmartRouterHatti().calistir(path, metin_dahil=True)
            merged = self._run_heavy_pages(path, decision)
        except Exception:
            # A malformed download must not abort acquisition; the caller rejects
            # the document on the resulting empty text instead.
            return ParsedDocument(document_type="pdf", parser_id=self.id)
        finally:
            self._discard(path)

        return ParsedDocument(
            text=sayfa_basliklariyla(merged),
            document_type="pdf",
            parser_id=self.id,
            page_count=merged.page_count,
        )

    def _run_heavy_pages(self, path: str, decision: dict) -> MergedDocument:
        """
        Send the flagged pages to the heavy engine and merge what comes back.

        The engine is optional and may be missing, time out, or return nothing for
        a page. None of those lose the page: it keeps its fast-path text and the
        merge records that it fell back, so a degraded document stays
        distinguishable from a clean one.
        """
        fast_pages = {int(k): v for k, v in (decision.get("sayfa_metni") or {}).items()}
        decisions = {
            int(page["sayfa_no"]): list(page.get("karar_kaynagi") or [])
            for page in decision.get("sayfalar") or []
        }
        heavy = sorted(page for page, reasons in decisions.items() if reasons)
        if not heavy:
            return birlestir(fast_pages, decisions=decisions)

        engine = DoclingEngine()
        usable, _ = engine.available()
        if not usable:
            return birlestir(fast_pages, decisions=decisions,
                             requested={engine.name: heavy})
        return birlestir(
            fast_pages, decisions=decisions,
            results=[engine.extract(path, heavy)],
            requested={engine.name: heavy},
        )

    def _spill_to_disk(self, content: bytes) -> str | None:
        """
        The router and every engine below it read a path, not a buffer.

        The handle is closed before the path is handed on: on Windows a second
        process cannot open a file we still hold open, so `delete=True` would make
        the engines fail rather than clean up after us.
        """
        try:
            handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        except OSError:
            return None
        try:
            handle.write(content)
        finally:
            handle.close()
        return handle.name

    def _discard(self, path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            # Losing a temp file is not worth failing an acquisition over.
            pass
