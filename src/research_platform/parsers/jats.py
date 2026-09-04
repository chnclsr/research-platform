from __future__ import annotations

from xml.etree import ElementTree

from .base import DocumentParser, ParsedDocument, ParsedTable

# Elements that carry prose but must not become their own heading, and elements whose
# whole subtree is apparatus rather than findings.
_INLINE = frozenset({
    "italic", "bold", "sup", "sub", "underline", "sc", "monospace", "roman",
    "xref", "ext-link", "uri", "email", "named-content", "styled-content",
})
_DROPPED = frozenset({
    "ref-list", "back", "journal-meta", "author-notes", "permissions",
    "fn-group", "glossary", "app-group", "notes", "funding-group",
})


def _local(tag: object) -> str:
    """Tag without its namespace. JATS is served both with and without one."""
    return str(tag).rsplit("}", 1)[-1]


def _mixed_text(element: ElementTree.Element) -> str:
    """Element text with inline markup flattened, INCLUDING each child's `tail`.

    `structured._flatten_xml` drops `element.tail`, so `<p>text <italic>x</italic> more</p>`
    loses " more" -- and JATS body prose is mixed content almost everywhere, so that loss
    is not an edge case. That function is deliberately not fixed here: `content_hash` is the
    sha256 of parsed text, so changing it would re-hash every XML source already stored.
    """
    parts: list[str] = [element.text or ""]
    for child in element:
        parts.append(_mixed_text(child))
        parts.append(child.tail or "")
    return " ".join("".join(parts).split())


def _is_jats(root: ElementTree.Element) -> bool:
    return _local(root.tag) in {"article", "pmc-articleset"}


class JatsParser(DocumentParser):
    """JATS XML (PMC full text) into headed markdown.

    Sits at priority 10 for `xml` so it outranks the priority-0 plain_text fallback, and
    sniffs for a JATS root in `can_parse` so generic XML keeps falling through to
    plain_text. Precedent for content sniffing: PyMuPdfParser.can_parse.
    """

    id = "jats_structured"
    document_types = ("xml",)
    capabilities = ("text", "sections", "tables")
    priority = 10

    def can_parse(self, document_type: str, content_type: str, content: bytes) -> bool:
        if document_type not in self.document_types:
            return False
        try:
            return _is_jats(ElementTree.fromstring(content.decode("utf-8", errors="replace")))
        except ElementTree.ParseError:
            return False

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        raw = content.decode("utf-8", errors="replace")
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError as exc:
            # A truncated download must degrade, not take the acquisition down with it.
            # The raw text still indexes; the provenance says why it was not structured.
            return ParsedDocument(
                text=raw,
                document_type="xml",
                parser_id=self.id,
                parse_provenance={"engine": "jats", "degraded": True, "notes": str(exc)},
            )
        if _local(root.tag) == "pmc-articleset":
            article = root.find("article")
            root = article if article is not None else root

        lines: list[str] = []
        tables: list[ParsedTable] = []
        state = {"sections": 0, "references_dropped": 0}

        title = root.find(".//article-meta/title-group/article-title")
        if title is not None:
            lines.append(f"# {_mixed_text(title)}")

        for abstract in root.findall(".//article-meta/abstract"):
            lines.append("## Abstract")
            self._render(abstract, lines, tables, state, depth=2, section_path="Abstract")

        body = root.find("body")
        if body is not None:
            self._render(body, lines, tables, state, depth=1, section_path="")

        state["references_dropped"] = len(root.findall(".//ref"))
        text = "\n\n".join(line for line in lines if line.strip())
        return ParsedDocument(
            text=text,
            document_type="xml",
            parser_id=self.id,
            tables=tables,
            parse_provenance={
                "engine": "jats",
                "sections": state["sections"],
                "references_dropped": state["references_dropped"],
            },
        )

    def _render(
        self,
        element: ElementTree.Element,
        lines: list[str],
        tables: list[ParsedTable],
        state: dict[str, int],
        *,
        depth: int,
        section_path: str,
    ) -> None:
        """Walk in document order only -- nothing here may iterate a set or a dict.

        `content_hash` is the sha256 of the emitted text and drives source-version dedup,
        MinIO keys and passage offsets, so a parse that reorders between runs would split
        one source into two.
        """
        for child in element:
            tag = _local(child.tag)
            if tag in _DROPPED:
                continue
            if tag == "sec":
                state["sections"] += 1
                heading = child.find("title")
                name = _mixed_text(heading) if heading is not None else ""
                level = min(depth + 1, 6)
                if name:
                    lines.append(f"{'#' * level} {name}")
                self._render(
                    child, lines, tables, state,
                    depth=level,
                    section_path=f"{section_path} > {name}" if section_path else name,
                )
            elif tag == "table-wrap":
                table = self._table(child, section_path)
                if table is not None:
                    tables.append(table)
                    lines.append(table.to_markdown())
            elif tag == "title":
                # Already emitted as this element's heading by the `sec` branch above (or
                # by the caller for an abstract). Rendering it again here would duplicate
                # every section heading as a paragraph directly beneath itself.
                continue
            elif tag == "p":
                text = _mixed_text(child)
                if text:
                    lines.append(text)
            elif tag in {"list", "list-item", "boxed-text", "statement", "disp-quote"}:
                self._render(
                    child, lines, tables, state, depth=depth, section_path=section_path
                )

    @staticmethod
    def _table(element: ElementTree.Element, section_path: str) -> ParsedTable | None:
        table = element.find(".//table")
        if table is None:
            return None
        rows: list[list[str]] = []
        for row in table.iter():
            if _local(row.tag) != "tr":
                continue
            cells = [
                _mixed_text(cell) for cell in row if _local(cell.tag) in {"td", "th"}
            ]
            if cells:
                rows.append(cells)
        if not rows:
            return None
        return ParsedTable(section_path=section_path, headers=rows[0], rows=rows[1:])
