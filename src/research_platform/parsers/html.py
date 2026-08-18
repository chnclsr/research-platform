from __future__ import annotations

import re
from html.parser import HTMLParser

from ..normalization import extract_links
from .base import DocumentParser, ParsedDocument, ParsedTable


class StructuredHTMLParser(HTMLParser):
    """
    Converts HTML into heading-aware markdown.

    Two structures get dedicated handling because collapsing them into prose destroys the
    information downstream stages need. Tables become pipe-delimited markdown so a figure
    stays attached to its column and row; code keeps its original whitespace because
    indentation is the meaning. Everything else is whitespace-normalised as before.
    """

    BLOCKS = {"p", "div", "section", "article", "li", "ul", "ol", "blockquote"}
    CELLS = {"td", "th"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0
        self.heading: int | None = None
        # Verbatim capture for <pre>/<code>; whitespace must survive untouched.
        self.pre_depth = 0
        self.pre_buffer: list[str] = []
        # Table state. Nested tables are flattened onto the innermost row.
        self.table_depth = 0
        self.tables: list[ParsedTable] = []
        self.rows: list[list[str]] = []
        self.row: list[str] = []
        self.cell: list[str] | None = None
        self.row_is_header = False
        self.header: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return
        if tag == "pre":
            self.pre_depth += 1
            self.pre_buffer = []
        elif tag == "table":
            self.table_depth += 1
            self.rows, self.header, self.row = [], [], []
        elif tag == "tr" and self.table_depth:
            self.row, self.row_is_header = [], False
        elif tag in self.CELLS and self.table_depth:
            self.cell = []
            if tag == "th":
                self.row_is_header = True
        elif re.fullmatch(r"h[1-6]", tag):
            self.heading = int(tag[1])
            self.parts.append("\n")
        elif tag in {"br", "hr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self.ignored_depth:
            self.ignored_depth -= 1
            return
        if self.ignored_depth:
            return
        if tag == "pre" and self.pre_depth:
            self.pre_depth -= 1
            self._flush_pre()
        elif tag in self.CELLS and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.table_depth:
            self._flush_row()
        elif tag == "table" and self.table_depth:
            self.table_depth -= 1
            self._flush_table()
        elif re.fullmatch(r"h[1-6]", tag):
            self.parts.append("\n")
            self.heading = None
        elif tag in self.BLOCKS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self.ignored_depth:
            return
        if self.pre_depth:
            self.pre_buffer.append(data)
            return
        if self.cell is not None:
            self.cell.append(data)
            return
        if not data.strip():
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if self.heading is not None and (not self.parts or self.parts[-1].endswith("\n")):
            self.parts.append(f"{'#' * self.heading} ")
        elif self.parts and not self.parts[-1].endswith((" ", "\n")):
            self.parts.append(" ")
        self.parts.append(cleaned)

    def _flush_pre(self) -> None:
        code = "".join(self.pre_buffer).strip("\n")
        self.pre_buffer = []
        if not code.strip():
            return
        self.parts.append(f"\n\n```\n{code}\n```\n\n")

    def _flush_row(self) -> None:
        if not self.row:
            return
        if self.row_is_header and not self.header:
            self.header = self.row
        else:
            self.rows.append(self.row)
        self.row = []

    def _flush_table(self) -> None:
        if self.row:
            self._flush_row()
        if not self.header and self.rows:
            # Header-less tables still deserve aligned columns; promote the first row.
            self.header, self.rows = self.rows[0], self.rows[1:]
        table = ParsedTable(headers=self.header, rows=self.rows)
        markdown = table.to_markdown()
        if markdown:
            self.tables.append(table)
            self.parts.append(f"\n\n{markdown}\n\n")
        self.header, self.rows, self.row = [], [], []

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html: str) -> str:
    parser = StructuredHTMLParser()
    parser.feed(html)
    return parser.markdown()


class HtmlParser(DocumentParser):
    id = "html"
    document_types = ("html",)
    capabilities = ("text", "sections", "tables", "code", "links")
    priority = 0

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        raw = content.decode("utf-8", errors="replace")
        parser = StructuredHTMLParser()
        try:
            parser.feed(raw)
        except Exception:
            # Malformed markup should degrade to whatever was parsed so far.
            pass
        links, canonical = extract_links(raw, url)
        code_blocks = re.findall(r"```\n(.*?)\n```", parser.markdown(), flags=re.S)
        return ParsedDocument(
            text=parser.markdown(),
            document_type="html",
            parser_id=self.id,
            tables=parser.tables,
            code_blocks=code_blocks,
            outgoing_links=links,
            canonical_url=canonical,
        )
