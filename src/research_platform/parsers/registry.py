from __future__ import annotations

from .base import DocumentParser, ParserHealth
from .html import HtmlParser
from .pdf import PdfParser
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
        self, document_type: str, content_type: str = "", content: bytes = b""
    ) -> DocumentParser | None:
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
    return ParserRegistry([HtmlParser(), PdfParser(), PlainTextParser()])
