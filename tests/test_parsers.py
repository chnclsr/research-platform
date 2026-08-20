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
# Table veto (gate.py::_v2_tablo_karari) -- pure function, no PyMuPDF page
# needed. CLAUDE-2026-08-20: extracted from GirisKapisi._cizim's inline logic
# specifically so these four cases could be pinned without a real PDF.
# ---------------------------------------------------------------------------

_TABLO_ESIK = {
    "ortogonal_cizgi": 6, "dolu_dikdortgen": 60,
    "izgara_sutun": 3, "izgara_satir": 4, "sekil_veto_kaplama": 0.15,
}


def test_table_veto_disabled_lets_ortogonal_count_even_with_no_drawings():
    """Regression guard: `sekil_veto_kaplama=0` must mean "off", not "always on".

    `kume_kaplama >= 0` is True for a page with no drawings at all
    (kume_kaplama defaults to 0.0), so a bare `>=` comparison made "disabled"
    behave like "veto every page with nothing on it" -- found reading the
    code, not from any measured run, because the threshold has always been
    positive in practice.
    """
    from research_platform.parsers.smart_router.gate import _v2_tablo_karari

    esik = dict(_TABLO_ESIK, sekil_veto_kaplama=0.0)
    cizim = {"ortogonal_cizgi": 6, "dolu_dikdortgen": 0}
    izgara = {"izgara_sutun": 0, "izgara_satir": 0}
    assert _v2_tablo_karari(cizim, izgara, kume_kaplama=0.0, esik=esik) is True


def test_table_veto_suppresses_ortogonal_inside_a_large_figure():
    """A large diagram's line count alone must not read as a table."""
    from research_platform.parsers.smart_router.gate import _v2_tablo_karari

    cizim = {"ortogonal_cizgi": 210, "dolu_dikdortgen": 43}
    izgara = {"izgara_sutun": 1, "izgara_satir": 0}
    assert _v2_tablo_karari(cizim, izgara, kume_kaplama=0.51, esik=_TABLO_ESIK) is False


def test_table_veto_still_catches_a_dense_filled_grid_inside_a_figure():
    """dolu_dikdortgen is not suppressed -- a real table can sit inside a
    large image region (measured: two benchmark pages, 66-105 filled
    rectangles each, both real tables)."""
    from research_platform.parsers.smart_router.gate import _v2_tablo_karari

    cizim = {"ortogonal_cizgi": 210, "dolu_dikdortgen": 66}
    izgara = {"izgara_sutun": 1, "izgara_satir": 0}
    assert _v2_tablo_karari(cizim, izgara, kume_kaplama=0.41, esik=_TABLO_ESIK) is True


def test_table_veto_does_not_hide_a_grid_signal_next_to_a_figure():
    """A page can have both a large figure and a separate, real table --
    the grid signal (word-spacing columns) is untouched by the veto."""
    from research_platform.parsers.smart_router.gate import _v2_tablo_karari

    cizim = {"ortogonal_cizgi": 300, "dolu_dikdortgen": 10}
    izgara = {"izgara_sutun": 4, "izgara_satir": 5}
    assert _v2_tablo_karari(cizim, izgara, kume_kaplama=0.6, esik=_TABLO_ESIK) is True


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
    assert ayar.kapi_esikleri["dolu_dikdortgen"] == 60
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
# profile value now (0.1 as of 2026-08-20, config/smart_router.yaml -- see
# entegrasyon_plani.md Bölüm 17 madde #1 for the page-by-page review behind
# that number); both `tolerans` values below are passed explicitly so this
# test does not depend on whatever the profile currently says.
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


# CLAUDE-2026-08-20: exactly at the boundary (heavy == fast - tolerans) must
# accept -- the comparison is `>=`, not `>`. Regression guard for that sign.
def test_merge_accepts_heavy_exactly_at_the_tolerance_boundary():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    heavy = EngineResult(engine="docling", pages={1: "heavy"})
    puan = {"fast": 100.0, "heavy": 99.9}.get  # fark tam olarak -0.1

    merged = birlestir({1: "fast"}, results=[heavy], requested={"docling": [1]},
                       score=puan, tolerans=0.1)
    assert merged.quarantined_pages == []
    assert merged.pages[0].engine == "docling"
    assert merged.pages[0].karar_gerekcesi.startswith("skor_farki_kabul")


# CLAUDE-2026-08-20: a formula marker on a page that ALSO collapsed in
# length is rejected regardless of the corruption score. No confirmed real
# example of this combination exists yet (see FORMUL_KATASTROFIK_UZUNLUK_ESIGI
# in merge.py -- the pages this check was originally written for turned out,
# on closer measurement, not to be collapsed at all); this pins the intended
# behaviour with a synthetic one so the branch has coverage. Fast is written
# long enough (>=30 chars, see ICERIK_KAYBI_TABAN_KARAKTER) for the
# length-ratio gate below to actually judge it, not abstain.
def test_merge_rejects_a_heavy_page_that_lost_a_formula_and_most_of_its_length():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    fast_metin = "Attention is computed by taking the dot product of queries and keys. " * 3
    heavy = EngineResult(engine="docling", pages={1: "<!-- formula-not-decoded -->"})
    puan = {fast_metin: 90.0, "<!-- formula-not-decoded -->": 95.0}.get  # heavy would win on score alone
    merged = birlestir({1: fast_metin}, results=[heavy], requested={"docling": [1]}, score=puan)
    assert merged.quarantined_pages == [1]
    assert merged.pages[0].karar_gerekcesi == "heavy_formul_cozulemedi"


# CLAUDE-2026-08-20: regression guard for a real C1 replay failure
# (01030000000110, entegrasyon_plani.md Bölüm 17) -- Docling lost one
# Reynolds-number formula but correctly extracted an entire data table fast
# had missed outright (heavy longer than fast, both scoring a clean 100 on
# corruption). The formula-only check rejected it anyway and cost 0.23 of
# measured utility. A formula marker must not veto a page heavy otherwise
# kept or grew.
def test_merge_does_not_reject_a_formula_marker_when_heavy_kept_the_rest_of_the_page():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    fast_metin = "The kinematic viscosity of water varies with temperature. " * 3
    heavy_metin = (
        "The kinematic viscosity of water varies with temperature.\n\n"
        "<!-- formula-not-decoded -->\n\n"
        "| Temperature | Viscosity |\n|---|---|\n| 0 | 1.79e-6 |\n| 25 | 8.9e-7 |\n"
    ) * 2
    heavy = EngineResult(engine="docling", pages={1: heavy_metin})
    merged = birlestir({1: fast_metin}, results=[heavy], requested={"docling": [1]},
                       score=lambda t: 100.0)
    assert merged.quarantined_pages == []
    assert merged.pages[0].engine == "docling"


# CLAUDE-2026-08-20: an already-present placeholder in fast (e.g. carried
# over from an earlier pass) must not itself trigger a reject -- the check
# only fires when heavy introduces the marker and fast did not already have it.
def test_merge_does_not_reject_for_a_formula_marker_already_present_in_fast():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    heavy = EngineResult(engine="docling", pages={1: "<!-- formula-not-decoded -->"})
    fast = {1: "some text <!-- formula-not-decoded --> already here"}
    puan = {fast[1]: 90.0, "<!-- formula-not-decoded -->": 90.0}.get
    merged = birlestir(fast, results=[heavy], requested={"docling": [1]}, score=puan)
    assert merged.quarantined_pages == []


# CLAUDE-2026-08-20: an OCR page has no fast text to fall back to, so a
# flagged-corrupt heavy result is still kept -- rejecting it would just leave
# the empty fast text, which is no better. Provenance has to say this was not
# a clean win, since there is no third engine to try today (MinerU is not
# wired in, see engines.py).
def test_merge_accepts_a_flagged_corrupt_heavy_page_when_fast_is_empty():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    heavy = EngineResult(engine="docling", pages={1: "<!-- formula-not-decoded -->"})
    merged = birlestir({1: ""}, results=[heavy], requested={"docling": [1]},
                       score=lambda t: 90.0)
    assert merged.quarantined_pages == []
    assert merged.pages[0].engine == "docling"
    assert merged.pages[0].karar_gerekcesi == "fast_bos_heavy_de_bozuk_alternatif_yok"
    assert merged.degraded is True
    assert any("no alternative engine" in n for n in merged.notes)


# CLAUDE-2026-08-20: a bare figure caption can score a clean corruption-check
# ACCEPT (no gibberish, no unicode noise) while silently dropping most of the
# page's real content -- measured on gpt4_uzun_gorsel pages 48/57/63/67 (82-97%
# loss) and independently on an unseen document (Codex's EUSO factsheet run,
# 47.2% loss). The score comparison alone would have accepted this page.
def test_merge_rejects_a_heavy_page_that_collapsed_in_length():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    fast_metin = "Bu sayfada gercek, uzun bir icerik var. " * 5  # > 30 karakter
    heavy = EngineResult(engine="docling", pages={1: "Figure 1: kisa baslik.\n\n<!-- image -->"})
    puan = {fast_metin: 90.0}.get
    merged = birlestir({1: fast_metin}, results=[heavy], requested={"docling": [1]},
                       score=lambda t: 100.0, icerik_kaybi_esik=0.20)
    assert merged.quarantined_pages == [1]
    assert merged.pages[0].karar_gerekcesi == "heavy_buyuk_icerik_kaybi"


# CLAUDE-2026-08-20: the check is opt-in via the profile (icerik_kaybi_esik),
# same shape as `tolerans` -- 0 (or omitted) must keep the old behaviour so a
# broken/absent profile does not start rejecting pages it never used to.
def test_merge_does_not_check_content_loss_when_the_threshold_is_zero():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    fast_metin = "Bu sayfada gercek, uzun bir icerik var. " * 5
    heavy = EngineResult(engine="docling", pages={1: "Figure 1: kisa baslik.\n\n<!-- image -->"})
    merged = birlestir({1: fast_metin}, results=[heavy], requested={"docling": [1]},
                       score=lambda t: 100.0, icerik_kaybi_esik=0.0)
    assert merged.quarantined_pages == []


# CLAUDE-2026-08-20: too little fast text to trust a ratio -- critic.py's own
# TOTAL_TEXT_DROPPED cutoff already treats under 30 characters as no text.
def test_merge_ignores_content_loss_ratio_when_fast_is_too_short_to_judge():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    heavy = EngineResult(engine="docling", pages={1: "x"})
    merged = birlestir({1: "kisa"}, results=[heavy], requested={"docling": [1]},
                       score=lambda t: 100.0, icerik_kaybi_esik=0.20)
    assert merged.quarantined_pages == []


# CLAUDE-2026-08-20: one-directional by construction -- heavy legitimately
# expanding a page (e.g. a compressed matrix rendered as full Markdown table
# rows, measured 6.3x on an unseen IRS form during the same Codex run) must
# never be read as a loss.
def test_merge_content_loss_check_never_fires_when_heavy_is_longer():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    fast_metin = "kisa metin " * 5
    heavy = EngineResult(engine="docling", pages={1: "cok daha uzun bir aciklama metni " * 20})
    merged = birlestir({1: fast_metin}, results=[heavy], requested={"docling": [1]},
                       score=lambda t: 100.0, icerik_kaybi_esik=0.20)
    assert merged.quarantined_pages == []


# CLAUDE-2026-08-20: an earlier engine's rejection must not outlive a later
# engine's acceptance of the same page -- CODEX-2026-08-18's table-leak fix
# covered the table side of this, quarantined_pages had the matching gap.
def test_merge_quarantine_does_not_survive_a_later_engine_accepting_the_page():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    ilk_deneme = EngineResult(engine="docling", pages={1: "bad heavy"})
    ikinci_deneme = EngineResult(engine="mineru", pages={1: "good heavy"})
    puan = {"fast": 90.0, "bad heavy": 10.0, "good heavy": 95.0}.get

    merged = birlestir(
        {1: "fast"}, results=[ilk_deneme, ikinci_deneme],
        requested={"docling": [1], "mineru": [1]}, score=puan,
    )
    assert merged.quarantined_pages == []
    assert merged.pages[0].engine == "mineru"


# CLAUDE-2026-08-19: Measured on an RTX 4060 box -- the same PDF and the same
# Docling build produce different text on CPU and CUDA, 4 of 9 corpus documents,
# one losing a whole markdown table. content_hash is the sha256 of that text, so a
# document parsed on one device is not interchangeable with the same document
# parsed on another and provenance has to say which ran.
def test_merge_carries_the_engine_device_into_provenance():
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    merged = birlestir(
        {1: "fast"},
        results=[EngineResult(engine="docling", pages={1: "heavy"}, device="cuda")],
        requested={"docling": [1]},
    )
    assert merged.engine_devices == {"docling": "cuda"}


def test_merge_reports_no_device_when_the_engine_did_not_name_one():
    """An unknown device must read as unknown, not as a default one."""
    from research_platform.parsers.smart_router.engines import EngineResult
    from research_platform.parsers.smart_router.merge import birlestir

    merged = birlestir(
        {1: "fast"},
        results=[EngineResult(engine="docling", pages={1: "heavy"})],
        requested={"docling": [1]},
    )
    assert merged.engine_devices == {}
