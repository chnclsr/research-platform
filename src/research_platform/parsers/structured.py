from __future__ import annotations

import json
from xml.etree import ElementTree

from .base import DocumentParser, ParsedDocument


def _flatten_json(value: object, path: str = "") -> list[str]:
    """
    Render JSON as `path: value` lines.

    Raw JSON reads poorly once chunked: braces and quotes dominate the token budget and a
    value can be separated from its key by a chunk boundary. One line per leaf keeps the
    key attached to its value no matter where the text is split.
    """
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            lines.extend(_flatten_json(item, f"{path}.{key}" if path else str(key)))
        return lines
    if isinstance(value, list):
        lines = []
        for index, item in enumerate(value):
            lines.extend(_flatten_json(item, f"{path}[{index}]"))
        return lines
    return [f"{path}: {value}" if path else str(value)]


def _flatten_xml(element: ElementTree.Element, path: str = "") -> list[str]:
    tag = element.tag.rsplit("}", 1)[-1]
    current = f"{path} > {tag}" if path else tag
    lines: list[str] = []
    for name, attribute in element.attrib.items():
        lines.append(f"{current}@{name}: {attribute}")
    text = (element.text or "").strip()
    if text:
        lines.append(f"{current}: {text}")
    for child in element:
        lines.extend(_flatten_xml(child, current))
    return lines


class PlainTextParser(DocumentParser):
    """Text, JSON and XML. JSON and XML are flattened into key-path lines."""

    id = "plain_text"
    document_types = ("text", "json", "xml")
    capabilities = ("text",)
    priority = 0

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        raw = content.decode("utf-8", errors="replace")
        header = content[:32].lstrip().lower()
        mime = content_type.lower()

        if header.startswith((b"{", b"[")) or "json" in mime:
            try:
                lines = _flatten_json(json.loads(raw))
                return ParsedDocument(
                    text="\n".join(lines), document_type="json", parser_id=self.id
                )
            except Exception:
                # Malformed JSON is still worth indexing as text.
                return ParsedDocument(text=raw, document_type="json", parser_id=self.id)

        if header.startswith(b"<?xml") or "xml" in mime:
            try:
                lines = _flatten_xml(ElementTree.fromstring(raw))
                return ParsedDocument(
                    text="\n".join(lines), document_type="xml", parser_id=self.id
                )
            except Exception:
                return ParsedDocument(text=raw, document_type="xml", parser_id=self.id)

        return ParsedDocument(text=raw, document_type="text", parser_id=self.id)
