from __future__ import annotations

from .base import DocumentParser, ParserHealth
from .html import HtmlParser
from .pdf import PdfParser
from .smart_pdf import SmartPdfParser
from .structured import PlainTextParser


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
            override = self._parsers.get(overrides.get(document_type, ""))
            if override is not None and override.can_parse(document_type, content_type, content):
                return override
        candidates = [
            parser
            for parser in self.parsers
            if parser.can_parse(document_type, content_type, content)
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda parser: (-parser.priority, parser.id))[0]

    def health(self) -> list[ParserHealth]:
        return [parser.health() for parser in self.parsers]


def build_parser_registry() -> ParserRegistry:
    return ParserRegistry([HtmlParser(), PdfParser(), SmartPdfParser(), PlainTextParser()])
