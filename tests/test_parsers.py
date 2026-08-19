"""
Conformance suite every parser must satisfy.

Parsers are contributed independently, so the contract lives here rather than in each
parser's own tests: whatever a parser does internally, it has to keep these promises or
the acquisition pipeline downstream of it breaks.
"""

from __future__ import annotations

import pytest

from research_platform.parsers import (
    DocumentParser,
    HtmlParser,
    ParsedDocument,
    ParsedTable,
    ParserRegistry,
    PlainTextParser,
    PyMuPdfParser,
    PyPdfParser,
    build_parser_registry,
)
from research_platform.passages import chunk_document


ALL_PARSERS = [HtmlParser(), PyMuPdfParser(), PyPdfParser(), PlainTextParser()]


@pytest.mark.parametrize("parser", ALL_PARSERS, ids=lambda p: p.id)
def test_parser_declares_a_usable_identity(parser):
    assert parser.id
    assert parser.document_types
    assert "text" in parser.capabilities
    health = parser.health()
    assert health.id == parser.id
    assert health.document_types == list(parser.document_types)


@pytest.mark.parametrize("parser", ALL_PARSERS, ids=lambda p: p.id)
def test_parser_survives_truncated_input(parser):
    """A corrupt download must not take the whole acquisition down with an exception."""
    for payload in (b"", b"\x00\x01\x02", b"<html><body>unclosed"):
        try:
            result = parser.parse(payload, url="https://example.org/x")
        except Exception as exc:  # noqa: BLE001 - the point is to report, not to hide
            pytest.fail(f"{parser.id} raised on {payload!r}: {exc}")
        assert isinstance(result.text, str)


@pytest.mark.parametrize("parser", ALL_PARSERS, ids=lambda p: p.id)
def test_parser_reports_its_own_id(parser):
    result = parser.parse(b"<html><body><p>hello world</p></body></html>", url="https://e.org")
    assert result.parser_id == parser.id


def test_registry_selects_deterministically_by_document_type():
    registry = build_parser_registry()
    assert registry.select("html", "text/html", b"<html>").id == "html_structured"
    assert registry.select("pdf", "application/pdf", b"%PDF-1.4").id == "pymupdf_fast"
    for document_type in ("json", "xml", "text"):
        assert registry.select(document_type, "", b"").id == "plain_text"
    assert registry.select("image", "image/png", b"\x89PNG") is None


def test_registry_selection_is_stable_across_calls():
    """content_hash and passage offsets depend on the same bytes yielding the same parser."""
    registry = build_parser_registry()
    picks = {registry.select("html", "text/html", b"<html>").id for _ in range(10)}
    assert picks == {"html_structured"}


def test_registry_exposes_parsers_by_id():
    registry = build_parser_registry()
    assert registry.get("html_structured") is not None
    assert registry.get("pymupdf_fast") is not None
    assert registry.get("pypdf") is not None
    assert registry.get("does-not-exist") is None
    assert {h.id for h in registry.health()} == {"html_structured", "pymupdf_fast", "pypdf", "plain_text"}


def test_html_parser_keeps_headings_so_chunking_can_build_section_paths():
    html = b"<h1>Alpha</h1><p>" + b"word " * 200 + b"</p><h2>Beta</h2><p>" + b"other " * 200 + b"</p>"
    parsed = HtmlParser().parse(html, url="https://example.org/doc")
    passages = chunk_document(parsed.text, "v1", target_tokens=120, overlap_tokens=20)
    section_paths = {p.section_path for p in passages}
    assert any("Alpha" in path for path in section_paths)
    assert any("Beta" in path for path in section_paths)


def test_html_parser_drops_scripts_and_styles():
    html = b"<html><body><script>evil()</script><style>.a{}</style><p>kept</p></body></html>"
    text = HtmlParser().parse(html, url="https://example.org").text
    assert "kept" in text
    assert "evil" not in text and ".a{}" not in text


def test_html_parser_extracts_outgoing_links():
    html = b'<html><body><a href="/next">n</a><p>body</p></body></html>'
    parsed = HtmlParser().parse(html, url="https://example.org/page")
    assert any("example.org/next" in link for link in parsed.outgoing_links)


def test_plain_text_parser_labels_json_and_xml():
    parser = PlainTextParser()
    assert parser.parse(b'{"a": 1}', url="https://e.org").document_type == "json"
    assert parser.parse(b"<?xml version='1.0'?><r/>", url="https://e.org").document_type == "xml"
    assert parser.parse(b"plain words", url="https://e.org").document_type == "text"


def test_parsed_table_renders_aligned_markdown():
    table = ParsedTable(headers=["Reactor", "Cost"], rows=[["NuScale", "20139"], ["BWRX"]])
    markdown = table.to_markdown()
    lines = markdown.splitlines()
    assert lines[0] == "| Reactor | Cost |"
    assert lines[1] == "| --- | --- |"
    # Short rows are padded so columns stay aligned.
    assert lines[3] == "| BWRX |  |"


def test_parsed_table_escapes_pipes_in_cells():
    table = ParsedTable(headers=["a|b"], rows=[["c|d"]])
    assert "a\\|b" in table.to_markdown()
    assert "c\\|d" in table.to_markdown()


def test_html_parser_keeps_table_columns_addressable():
    """Collapsing a table into prose loses which number belongs to which column."""
    html = (
        b"<table>"
        b"<tr><th>Reactor</th><th>Cost</th></tr>"
        b"<tr><td>NuScale</td><td>20139</td></tr>"
        b"</table>"
    )
    parsed = HtmlParser().parse(html, url="https://example.org")
    assert "| Reactor | Cost |" in parsed.text
    assert "| NuScale | 20139 |" in parsed.text
    assert len(parsed.tables) == 1
    assert parsed.tables[0].headers == ["Reactor", "Cost"]
    assert parsed.tables[0].rows == [["NuScale", "20139"]]


def test_html_parser_promotes_first_row_when_table_has_no_header_cells():
    html = b"<table><tr><td>a</td><td>b</td></tr><tr><td>1</td><td>2</td></tr></table>"
    parsed = HtmlParser().parse(html, url="https://example.org")
    assert parsed.tables[0].headers == ["a", "b"]
    assert parsed.tables[0].rows == [["1", "2"]]


def test_html_parser_keeps_code_indentation_and_fences_it():
    html = b"<pre><code>def f():\n    return 1\n</code></pre>"
    parsed = HtmlParser().parse(html, url="https://example.org")
    assert "```" in parsed.text
    assert "    return 1" in parsed.text
    assert parsed.code_blocks and "    return 1" in parsed.code_blocks[0]


def test_html_parser_still_collapses_ordinary_prose_whitespace():
    html = b"<p>one\n\n   two</p>"
    assert HtmlParser().parse(html, url="https://example.org").text == "one two"


def test_plain_text_parser_flattens_json_into_key_paths():
    payload = b'{"study": {"cost": 20139, "authors": ["a", "b"]}}'
    text = PlainTextParser().parse(payload, url="https://e.org").text
    assert "study.cost: 20139" in text
    assert "study.authors[0]: a" in text


def test_plain_text_parser_flattens_xml_into_paths():
    # detect_document_type only calls a payload XML when it declares itself or the MIME
    # type says so, so that is how it reaches the parser in the pipeline.
    payload = b"<root><item id='1'>value</item></root>"
    text = PlainTextParser().parse(payload, url="https://e.org", content_type="application/xml").text
    assert "root > item@id: 1" in text
    assert "root > item: value" in text


def test_plain_text_parser_falls_back_to_raw_on_malformed_payloads():
    broken = b'{"unclosed": '
    result = PlainTextParser().parse(broken, url="https://e.org")
    assert result.document_type == "json"
    assert "unclosed" in result.text


def test_pdf_parsers_report_availability():
    pymupdf = PyMuPdfParser()
    pypdf = PyPdfParser()
    assert pymupdf.id == "pymupdf_fast"
    assert pypdf.id == "pypdf"
    assert pypdf.available()[0] is True


class _AlternativeHtmlParser(DocumentParser):
    """Stands in for a contributed second HTML parser, which is the case overrides exist for."""

    id = "html_alt"
    document_types = ("html",)

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        return ParsedDocument(text="alt", document_type="html", parser_id=self.id)


def _two_html_parsers() -> ParserRegistry:
    return ParserRegistry([HtmlParser(), _AlternativeHtmlParser(), PyMuPdfParser(), PyPdfParser()])


def test_registry_honours_an_explicit_override():
    """ParserSelection lets a protocol name a parser without the LLM choosing per run."""
    registry = _two_html_parsers()
    assert registry.select("html", "text/html", b"<html>").id == "html_structured"
    assert registry.select("html", "text/html", b"<html>", {"html": "html_alt"}).id == "html_alt"
    assert registry.select("pdf", "application/pdf", b"%PDF", {"pdf": "pypdf"}).id == "pypdf"


def test_registry_supports_legacy_overrides_aliases():
    registry = build_parser_registry()
    assert registry.select("pdf", "application/pdf", b"%PDF", {"pdf": "pdf"}).id == "pymupdf_fast"
    assert registry.select("html", "text/html", b"<html>", {"html": "html"}).id == "html_structured"


def test_registry_ignores_an_unknown_override_instead_of_failing():
    registry = build_parser_registry()
    assert registry.select("html", "text/html", b"<html>", {"html": "nope"}).id == "html_structured"


def test_registry_rejects_an_override_that_cannot_handle_the_document_type():
    """A mismatched override would feed PDF bytes to the HTML parser and emit garbage."""
    registry = build_parser_registry()
    chosen = registry.select("pdf", "application/pdf", b"%PDF-1.4", {"pdf": "html_structured"})
    assert chosen.id == "pymupdf_fast"


def test_registry_override_only_applies_to_the_named_document_type():
    registry = _two_html_parsers()
    assert registry.select("pdf", "application/pdf", b"%PDF", {"html": "html_alt"}).id == "pymupdf_fast"
