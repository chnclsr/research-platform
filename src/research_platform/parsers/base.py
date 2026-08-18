from __future__ import annotations

from abc import ABC, abstractmethod

from typing import Any

from pydantic import BaseModel, Field


class ParsedTable(BaseModel):
    """A table recovered from a document, kept separately from the prose."""

    section_path: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)

    def to_markdown(self) -> str:
        if not self.headers and not self.rows:
            return ""
        width = max([len(self.headers), *(len(row) for row in self.rows)] or [0])
        if not width:
            return ""

        def line(cells: list[str]) -> str:
            padded = [*cells, *([""] * (width - len(cells)))]
            return "| " + " | ".join(cell.replace("|", "\\|") for cell in padded) + " |"

        header = self.headers or [""] * width
        return "\n".join(
            [line(header), "| " + " | ".join(["---"] * width) + " |", *(line(r) for r in self.rows)]
        )


class ParsedDocument(BaseModel):
    """
    Structured result of parsing one acquired document.

    `text` is the canonical extraction every downstream stage consumes: it feeds
    chunk_document() and, through it, passage offsets and claim locators. The optional
    fields carry structure that would otherwise be flattened into prose.
    """

    text: str = ""
    document_type: str = "text"
    parser_id: str = ""
    tables: list[ParsedTable] = Field(default_factory=list)
    code_blocks: list[str] = Field(default_factory=list)
    outgoing_links: list[str] = Field(default_factory=list)
    canonical_url: str | None = None
    page_count: int | None = None
    # How this document was parsed, for parsers that do more than run one extractor:
    # which profile produced it, which engine handled each page, whether anything
    # degraded. `parser_id` is a single string for the whole document, so a parser
    # that mixes engines has nowhere else to record that. Free-form on purpose --
    # it is carried to SourceVersion.provenance, which is a JSON column, so adding
    # keys here needs no migration. It is NOT part of content_hash: the hash comes
    # from the parsed text alone, and folding the profile in would make the same
    # text look like a new version whenever calibration changed.
    parse_provenance: dict[str, Any] = Field(default_factory=dict)


class ParserHealth(BaseModel):
    id: str
    document_types: list[str]
    capabilities: list[str]
    priority: int
    available: bool
    detail: str = ""


class DocumentParser(ABC):
    """
    Turns raw acquired bytes into a ParsedDocument.

    Mirrors the SourceConnector contract in connectors/base.py on purpose: class-level
    identity and capability declaration, one abstract method, and optional behaviour
    supplied by defaults. Contributors adding a parser only implement `parse`.
    """

    id: str
    document_types: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ("text",)
    # Higher wins when several parsers accept the same document type.
    priority: int = 0

    def can_parse(self, document_type: str, content_type: str, content: bytes) -> bool:
        return document_type in self.document_types

    def available(self) -> tuple[bool, str]:
        """Report optional-dependency status without raising."""
        return True, "configured"

    def health(self) -> ParserHealth:
        available, detail = self.available()
        return ParserHealth(
            id=self.id,
            document_types=list(self.document_types),
            capabilities=list(self.capabilities),
            priority=self.priority,
            available=available,
            detail=detail,
        )

    @abstractmethod
    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument: ...
