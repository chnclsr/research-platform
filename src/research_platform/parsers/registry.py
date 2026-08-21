from __future__ import annotations

from .base import DocumentParser, ParserHealth
from .html import HtmlParser
from .pdf import PdfParser, PyMuPdfParser, PyPdfParser
from .smart_pdf import SmartPdfParser
from .structured import PlainTextParser


# Priority scale. `candidates()` sorts by (-priority, id), so two parsers on the same
# level are separated by their id alphabetically -- which is a coin toss dressed up as a
# rule. The levels are therefore spaced, and what each one means is written down:
#
#   0  = fallback, used only when nothing else accepts the document (pypdf, plain_text)
#   10 = default single-pass extractor for a type (pymupdf_fast, html_structured)
#   20 = page router, deliberately ahead of the single-pass extractor (smart_pdf)
#
# The scale exists because two branches independently moved a parser to 10 without either
# doing anything wrong, and the tie put the router behind the plain extractor: no error,
# no exception, page routing simply switched itself off. A parser that has to sit off
# these levels should say why in a comment next to its `priority`.
class ParserRegistry:
    """
    Deterministic parser lookup, mirroring ConnectorRegistry in connectors/registry.py.

    Selection must stay deterministic: content_hash is derived from parsed text
    (acquisition.py) and drives source-version dedup, MinIO snapshot keys and passage
    offsets, so the same bytes have to yield the same parser on every run.
    """

    def __init__(self, parsers: list[DocumentParser]):
        self._parsers = {parser.id: parser for parser in parsers}

    @property
    def parsers(self) -> list[DocumentParser]:
        return list(self._parsers.values())

    def get(self, parser_id: str) -> DocumentParser | None:
        return self._parsers.get(parser_id)

    def candidates(
        self,
        document_type: str,
        content_type: str = "",
        content: bytes = b"",
    ) -> list[DocumentParser]:
        """Return all available parsers capable of parsing this document, sorted by priority."""
        matches = [
            parser
            for parser in self.parsers
            if parser.can_parse(document_type, content_type, content)
        ]
        return sorted(matches, key=lambda parser: (-parser.priority, parser.id))

    def select(
        self,
        document_type: str,
        content_type: str = "",
        content: bytes = b"",
        overrides: dict[str, str] | None = None,
    ) -> DocumentParser | None:
        # An override is an explicit, recorded decision (ParserSelection on the protocol).
        # It still has to accept the document: an id that cannot parse this type would
        # silently emit garbage, so it is treated exactly like an unknown id and falls
        # back to the deterministic pick rather than failing the run.
        if overrides:
            requested = overrides.get(document_type, "")
            override = self._parsers.get(requested)
            # Legacy alias support: if override is "pdf" or "html", map to top candidate
            if override is None and requested in {"pdf", "html"}:
                cands = self.candidates(document_type, content_type, content)
                if cands:
                    return cands[0]
            if override is not None and override.can_parse(document_type, content_type, content):
                return override
        cands = self.candidates(document_type, content_type, content)
        return cands[0] if cands else None

    def health(self) -> list[ParserHealth]:
        return [parser.health() for parser in self.parsers]


def build_parser_registry() -> ParserRegistry:
    return ParserRegistry([
        HtmlParser(),
        SmartPdfParser(),
        PyMuPdfParser(),
        PyPdfParser(),
        PlainTextParser(),
    ])
