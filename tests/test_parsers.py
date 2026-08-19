"""
Conformance suite every parser must satisfy.

Parsers are contributed independently, so the contract lives here rather than in each
parser's own tests: whatever a parser does internally, it has to keep these promises or
the acquisition pipeline downstream of it breaks.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from research_platform.parsers import (
    DocumentParser, ParsedDocument, ParsedTable, ParserRegistry, build_parser_registry,
)
from research_platform.parsers.html import HtmlParser
from research_platform.parsers.pdf import PdfParser
from research_platform.parsers.smart_pdf import SmartPdfParser
from research_platform.parsers.structured import PlainTextParser
from research_platform.passages import chunk_document


ALL_PARSERS = [HtmlParser(), PdfParser(), SmartPdfParser(), PlainTextParser()]


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
    assert registry.select("html", "text/html", b"<html>").id == "html"
    # smart_pdf outranks pdf on priority; both accept "pdf", the pick stays deterministic.
    assert registry.select("pdf", "application/pdf", b"%PDF-1.4").id == "smart_pdf"
    for document_type in ("json", "xml", "text"):
        assert registry.select(document_type, "", b"").id == "plain_text"
    assert registry.select("image", "image/png", b"\x89PNG") is None


# CODEX-2026-08-18: The smart parser must decline PDFs when its router import
# failed, otherwise its priority turns a usable plain parse into empty text.
def test_registry_falls_back_when_smart_router_is_unavailable(monkeypatch):
    import research_platform.parsers.smart_pdf as smart_pdf

    monkeypatch.setattr(smart_pdf, "SmartRouterHatti", None)
    registry = build_parser_registry()
    assert registry.select("pdf", "application/pdf", b"%PDF-1.4").id == "pdf"


def test_pdf_page_numbers_survive_nested_headings():
    """
    A page heading has to outrank whatever headings the page itself contains.

    chunk_document() reads page_number off the section path, and _sections() drops
    every ancestor at or above a heading's level -- so a heading inside a page can
    push "Page N" out of the path, and the passages after it lose their page number
    silently rather than raising. Both parsers that emit page headings depend on
    this, so the check lives with the contract.
    """
    content = "\n\n".join([
        "# Page 1", "intro " * 40,
        "## Section A", "body " * 40,
        "### Subsection B", "body " * 40,
        "# Page 2", "more " * 40,
        "## Section C", "body " * 40,
    ])
    passages = chunk_document(content, "v1", target_tokens=30, overlap_tokens=5)
    assert passages, "expected the fixture to produce passages"
    for passage in passages:
        expected = 1 if passage.section_path.startswith("Page 1") else 2
        assert passage.page_number == expected, (
            f"{passage.section_path!r} lost its page number"
        )


def test_parse_provenance_defaults_to_empty_and_survives_serialisation():
    """
    Provenance rides to SourceVersion.provenance, a JSON column, so it has to
    serialise -- and single-extractor parsers must not be forced to invent one.
    """
    plain = PlainTextParser().parse(b"words go here", url="https://e.org")
    assert plain.parse_provenance == {}

    routed = ParsedDocument(
        text="x", parser_id="smart_pdf",
        parse_provenance={"parser_profile": "inspector_v1",
                          "pages": [{"page": 1, "engine": "docling"}]},
    )
    assert routed.model_dump(mode="json")["parse_provenance"]["parser_profile"] == "inspector_v1"


def test_parsers_are_safe_to_share_across_threads():
    """
    Acquisition calls parse() through asyncio.to_thread, so one parser instance can
    be running several documents at once. Anything cached on the instance -- a temp
    path, an engine handle -- would make the results depend on the interleaving.
    """
    payloads = [
        b"<html><body><p>" + b"alpha " * 200 + b"</p></body></html>",
        b"<html><body><p>" + b"beta " * 200 + b"</p></body></html>",
        b"<html><body><p>" + b"gamma " * 200 + b"</p></body></html>",
    ]
    for parser in ALL_PARSERS:
        sequential = [parser.parse(p, url="https://e.org").text for p in payloads]
        with ThreadPoolExecutor(max_workers=3) as pool:
            concurrent = list(pool.map(
                lambda p: parser.parse(p, url="https://e.org").text, payloads
            ))
        assert concurrent == sequential, f"{parser.id} is not safe to share"


def test_merge_does_not_quarantine_a_page_for_having_produced_a_table():
    """
    The output check must not undo the routing it protects.

    Scoring both versions with the composite quality score reversed the decision on
    real pages: a fast path that emitted no table scored 92.4 with
    table_irregularity 0.000, while the engine that actually read the table scored
    85.3 with 0.368 -- penalised for having produced one. The comparison has to
    stay blind to signals that only fire once content exists.
    """
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir
    from research_platform.parsers.smart_pdf import SmartPdfParser

    fast = {1: "Table 1. Distribution of the sample."}
    heavy = EngineResult(engine="docling", pages={1: (
        "Table 1. Distribution of the sample.\n\n"
        "| Variable | N | % |\n| --- | --- | --- |\n| Male | 40 | 31.3 |\n"
    )})
    merged = birlestir(
        fast, results=[heavy], requested={"docling": [1]},
        score=SmartPdfParser()._page_scorer(),
    )
    assert merged.quarantined_pages == []
    assert merged.pages[0].engine == "docling"


# CODEX-2026-08-18: Structured output must follow the accepted page text.
def test_merge_drops_tables_from_a_quarantined_heavy_page():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    heavy = EngineResult(
        engine="docling", pages={1: "broken"},
        tables=[{"page": 1, "headers": ["A"], "rows": [["1"]]}],
    )
    merged = birlestir(
        {1: "clean fast text"}, results=[heavy], requested={"docling": [1]},
        score=lambda text: 100.0 if "clean" in text else 0.0,
    )
    assert merged.quarantined_pages == [1]
    assert merged.tables == []


def test_registry_selection_is_stable_across_calls():
    """content_hash and passage offsets depend on the same bytes yielding the same parser."""
    registry = build_parser_registry()
    picks = {registry.select("html", "text/html", b"<html>").id for _ in range(10)}
    assert picks == {"html"}


def test_registry_exposes_parsers_by_id():
    registry = build_parser_registry()
    assert registry.get("html") is not None
    assert registry.get("does-not-exist") is None
    assert {h.id for h in registry.health()} == {"html", "pdf", "smart_pdf", "plain_text"}


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


def test_pdf_parser_reports_which_backend_it_uses():
    available, detail = PdfParser().available()
    assert available
    assert "PyMuPDF" in detail or "pypdf" in detail


class _AlternativeHtmlParser(DocumentParser):
    """Stands in for a contributed second HTML parser, which is the case overrides exist for."""

    id = "html_alt"
    document_types = ("html",)

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        return ParsedDocument(text="alt", document_type="html", parser_id=self.id)


def _two_html_parsers() -> ParserRegistry:
    return ParserRegistry([HtmlParser(), _AlternativeHtmlParser(), PdfParser()])


def test_registry_honours_an_explicit_override():
    """ParserSelection lets a protocol name a parser without the LLM choosing per run."""
    registry = _two_html_parsers()
    assert registry.select("html", "text/html", b"<html>").id == "html"
    assert registry.select("html", "text/html", b"<html>", {"html": "html_alt"}).id == "html_alt"


def test_registry_ignores_an_unknown_override_instead_of_failing():
    registry = build_parser_registry()
    assert registry.select("html", "text/html", b"<html>", {"html": "nope"}).id == "html"


def test_registry_rejects_an_override_that_cannot_handle_the_document_type():
    """A mismatched override would feed PDF bytes to the HTML parser and emit garbage."""
    registry = build_parser_registry()
    chosen = registry.select("pdf", "application/pdf", b"%PDF-1.4", {"pdf": "html"})
    assert chosen.id == "smart_pdf"


def test_registry_override_only_applies_to_the_named_document_type():
    registry = _two_html_parsers()
    assert registry.select("pdf", "application/pdf", b"%PDF", {"html": "html_alt"}).id == "pdf"


# ---------------------------------------------------------------------------
# Threshold profile (config/smart_router.yaml)
# ---------------------------------------------------------------------------
# The version string used to be hand-written, so it could describe values it no
# longer matched and provenance would be wrong without anything failing. These
# pin the two properties that replaced it: the version follows the values, and a
# broken profile costs the profile rather than the pipeline.

def _profil(tmp_path, govde: str):
    yol = tmp_path / "smart_router.yaml"
    yol.write_text(govde, encoding="utf-8")
    return str(yol)


def test_threshold_profile_version_follows_the_values(tmp_path):
    from research_platform.parsers.smart_router import ayarlari_yukle

    taban = ayarlari_yukle("/nonexistent/profile.yaml")
    degisik = ayarlari_yukle(_profil(tmp_path, "kapi:\n  tablo:\n    ortogonal_cizgi: 4\n"))

    assert degisik.kapi_esikleri["ortogonal_cizgi"] == 4
    assert degisik.esik_version != taban.esik_version, (
        "a threshold moved but the version did not; provenance would be wrong"
    )


def test_a_profile_restating_the_defaults_keeps_the_same_version(tmp_path):
    """The version describes behaviour, so identical behaviour is the same version."""
    from research_platform.parsers.smart_router import ayarlari_yukle

    taban = ayarlari_yukle("/nonexistent/profile.yaml")
    ayni = ayarlari_yukle(_profil(
        tmp_path, "yonlendirme:\n  kalite_esik: 75.0\n# yorum surumu degistirmez\n"))
    assert ayni.esik_version == taban.esik_version


def test_a_broken_profile_falls_back_to_defaults_and_says_so(tmp_path):
    """A typo in a config file must not take PDF parsing down."""
    from research_platform.parsers.smart_router import ayarlari_yukle
    from research_platform.parsers.smart_router.ayarlar import VARSAYILAN

    ayar = ayarlari_yukle(_profil(tmp_path, "kapi: [bu bir sozluk degil\n"))
    assert ayar.kalite_esik == VARSAYILAN["yonlendirme"]["kalite_esik"]
    assert ayar.uyarilar, "the fallback happened silently"


def test_a_bad_value_costs_that_value_not_the_whole_profile(tmp_path):
    """The other thresholds in the file are still better than the defaults."""
    from research_platform.parsers.smart_router import ayarlari_yukle

    ayar = ayarlari_yukle(_profil(tmp_path, (
        "kapi:\n"
        "  tablo:\n"
        "    ortogonal_cizgi: 4\n"
        "    dolu_dikdortgen: -3\n"      # negative: nonsense for a count
        "  sekil:\n"
        "    bilinmeyen_anahtar: 1\n"    # typo: must not look configured
    )))
    assert ayar.kapi_esikleri["ortogonal_cizgi"] == 4
    assert ayar.kapi_esikleri["dolu_dikdortgen"] == 8
    assert "bilinmeyen_anahtar" not in ayar.kapi_esikleri
    assert len(ayar.uyarilar) == 2


def test_the_active_profile_reaches_provenance():
    """An operator has to be able to tell which thresholds parsed a document."""
    from research_platform.parsers.smart_router import AYAR

    ozet = AYAR.ozet()
    assert ozet["esik_version"] == AYAR.esik_version
    assert ozet["kaynak"]


# CODEX/CLAUDE: the quarantine rule had no dead band, so a tie decided in the
# third decimal threw away the heavy page and its table grid. The band is a
# profile value now; 0.0 keeps every measurement taken so far valid.
def test_merge_dead_band_keeps_a_heavy_page_that_scored_marginally_lower():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    heavy = EngineResult(engine="docling", pages={1: "heavy"})
    puan = {"fast": 90.0, "heavy": 89.98}.get

    sifir = birlestir({1: "fast"}, results=[heavy], requested={"docling": [1]},
                      score=puan, tolerans=0.0)
    assert sifir.quarantined_pages == [1]

    bant = birlestir({1: "fast"}, results=[heavy], requested={"docling": [1]},
                     score=puan, tolerans=0.5)
    assert bant.quarantined_pages == []
    assert bant.pages[0].engine == "docling"
