"""
How Docling pages become text: HTML escaping, and (later) formula/picture placeholders.

Docling is not installed in the test interpreter, so its converter is replaced by a
stand-in module. What is under test is our side of the contract: which arguments reach
`export_to_markdown`, and that every Docling path goes through the same helper.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class _SahteDokuman:
    """Records how it was rendered; escapes like Docling does unless told not to."""

    def __init__(self, metin: str = "Lime is recommended if pH < 5.8") -> None:
        self.metin = metin
        self.cagrilar: list[dict] = []
        self.tables: list = []

    def export_to_markdown(self, **kwargs):
        self.cagrilar.append(kwargs)
        if kwargs.get("escape_html", True):
            return self.metin.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return self.metin


def _sahte_docling(monkeypatch, dokuman: _SahteDokuman) -> None:
    class DocumentConverter:
        def convert(self, pdf_path, page_range=None):
            return types.SimpleNamespace(document=dokuman)

    paket = types.ModuleType("docling")
    modul = types.ModuleType("docling.document_converter")
    modul.DocumentConverter = DocumentConverter
    monkeypatch.setitem(sys.modules, "docling", paket)
    monkeypatch.setitem(sys.modules, "docling.document_converter", modul)


def test_page_markdown_is_not_html_escaped():
    from research_platform.parsers.smart_router._docling_worker import sayfa_markdown

    dokuman = _SahteDokuman()
    assert sayfa_markdown(dokuman, 3) == "Lime is recommended if pH < 5.8"
    assert dokuman.cagrilar == [{"page_no": 3, "escape_html": False}]


def test_the_bridged_worker_renders_pages_unescaped(monkeypatch):
    from research_platform.parsers.smart_router import _docling_worker

    dokuman = _SahteDokuman()
    _sahte_docling(monkeypatch, dokuman)
    sonuc = _docling_worker.run("belge.pdf", [[1, 2]])
    assert sonuc["pages"] == {1: "Lime is recommended if pH < 5.8",
                              2: "Lime is recommended if pH < 5.8"}
    assert all(c.get("escape_html") is False for c in dokuman.cagrilar)


def test_the_in_process_path_renders_pages_unescaped(monkeypatch):
    from research_platform.parsers.smart_router.engines import DoclingEngine

    dokuman = _SahteDokuman("R&D spending < 5%")
    _sahte_docling(monkeypatch, dokuman)
    pages, _tables, error, _, _, _regions = DoclingEngine()._in_process("belge.pdf", [(4, 4)])
    assert error is None
    assert pages == {4: "R&D spending < 5%"}


def test_no_docling_path_calls_export_to_markdown_directly():
    """
    The service script imports torch and docling at module level, so it cannot be run
    here; this guards it (and the other two paths) from bypassing the shared helper,
    which is what would bring `&lt;` back into one path while the others stay clean.
    """
    yollar = [
        REPO / "scripts" / "docling_service.py",
        REPO / "src" / "research_platform" / "parsers" / "smart_router" / "engines.py",
    ]
    for yol in yollar:
        assert ".export_to_markdown(" not in yol.read_text(encoding="utf-8"), yol.name
    worker = (REPO / "src" / "research_platform" / "parsers" / "smart_router"
              / "_docling_worker.py").read_text(encoding="utf-8")
    assert worker.count(".export_to_markdown(") == 1  # the helper itself


# --- Formula / picture regions and the placeholders that point at them -------------

FORMUL = "<!-- formula-not-decoded -->"
GORSEL = "<!-- image -->"


class _Kutu:
    def __init__(self, sol, ust, sag, alt):
        self.l, self.t, self.r, self.b = sol, ust, sag, alt

    def to_top_left_origin(self, page_height):
        return self


def _oge(etiket, *, text="", orig="", kutu=(50, 100, 300, 140), caption="", sayfa=1):
    oge = types.SimpleNamespace(
        label=types.SimpleNamespace(value=etiket), text=text, orig=orig,
        prov=[types.SimpleNamespace(page_no=sayfa, bbox=_Kutu(*kutu))],
    )
    oge.caption_text = lambda _dokuman: caption
    return oge


class _BolgeDokumani:
    def __init__(self, ogeler):
        self.ogeler = ogeler
        self.pages = {1: types.SimpleNamespace(size=types.SimpleNamespace(height=792.0))}
        self.istenen = []

    def iterate_items(self, page_no=None, included_content_layers=None):
        self.istenen.append(page_no)
        return [(o, 0) for o in self.ogeler if o.prov[0].page_no == page_no]


def test_regions_list_only_what_the_serializer_prints_a_marker_for():
    from research_platform.parsers.smart_router._docling_worker import sayfa_bolgeleri

    dokuman = _BolgeDokumani([
        _oge("text", text="Body paragraph"),
        _oge("formula", orig="x = v.t", kutu=(56, 60, 200, 80)),   # undecoded -> marker
        _oge("formula", text="x = 1", orig="x = 1"),               # decoded -> LaTeX, no marker
        _oge("formula", orig=""),                                  # serializer prints nothing
        _oge("picture", kutu=(112, 93, 469, 259), caption="Figure 1.6.  Work permits"),
        _oge("picture", kutu=(56, 476, 76, 496)),                  # 20x20 pt icon
    ])
    bolgeler = sayfa_bolgeleri(dokuman, 1)

    assert dokuman.istenen == [1]
    assert [b["tur"] for b in bolgeler] == ["formul", "gorsel", "gorsel"]
    assert bolgeler[0] == {"tur": "formul", "page": 1, "bbox": [56.0, 60.0, 200.0, 80.0]}
    assert bolgeler[1]["caption"] == "Figure 1.6. Work permits"
    assert bolgeler[1]["ikon"] is False
    assert bolgeler[2]["ikon"] is True


def _heavy(pages, regions):
    from research_platform.parsers.smart_router.engines import EngineResult

    return EngineResult(engine="docling", pages=pages, regions=regions)


def test_placeholders_are_numbered_across_pages_and_icons_disappear():
    from research_platform.parsers.smart_router.merge import birlestir

    heavy = _heavy(
        {1: f"Intro\n\n{FORMUL}\n\nMiddle\n\n{GORSEL}\n\nEnd",
         2: f"Then {FORMUL} holds.\n\n{GORSEL}\n\nTail"},
        [{"tur": "formul", "page": 1, "bbox": [1, 2, 3, 4]},
         {"tur": "gorsel", "page": 1, "bbox": [5, 6, 7, 8], "caption": "Fig 1", "ikon": False},
         {"tur": "formul", "page": 2, "bbox": [9, 9, 9, 9]},
         {"tur": "gorsel", "page": 2, "bbox": [0, 0, 20, 20], "caption": "", "ikon": True}],
    )
    merged = birlestir({1: "fast one", 2: "fast two"}, results=[heavy],
                       requested={"docling": [1, 2]}, score=lambda t: 100.0)

    sayfa1, sayfa2 = merged.pages[0].text, merged.pages[1].text
    assert sayfa1 == "Intro\n\n[formül 1]\n\nMiddle\n\n[görsel 1]\n\nEnd"
    assert sayfa2 == "Then [formül 2] holds.\n\nTail"
    assert "<!--" not in sayfa1 + sayfa2
    assert [(b["tur"], b["sira"], b["page"]) for b in merged.bolgeler] == [
        ("formul", 1, 1), ("gorsel", 1, 1), ("formul", 2, 2)]


def test_a_marker_count_that_does_not_match_the_regions_stays_unnumbered():
    from research_platform.parsers.smart_router.merge import birlestir

    heavy = _heavy({1: f"a {FORMUL} b {FORMUL} c"},
                   [{"tur": "formul", "page": 1, "bbox": [1, 2, 3, 4]}])
    merged = birlestir({1: "fast"}, results=[heavy], requested={"docling": [1]},
                       score=lambda t: 100.0)

    assert merged.pages[0].text == "a [formül] b [formül] c"
    assert merged.bolgeler == []
    assert any("left unnumbered" in note for note in merged.notes)


def test_an_older_service_without_regions_still_gets_no_html_comment():
    from research_platform.parsers.smart_router.merge import birlestir

    merged = birlestir({1: "fast"}, results=[_heavy({1: f"x {GORSEL} y"}, [])],
                       requested={"docling": [1]}, score=lambda t: 100.0)
    assert merged.pages[0].text == "x [görsel] y"


def test_a_quarantined_heavy_page_contributes_no_regions():
    from research_platform.parsers.smart_router.merge import birlestir

    fast = "The fast path read this page cleanly enough to keep it."
    heavy = _heavy({1: f"garbled {FORMUL}"}, [{"tur": "formul", "page": 1, "bbox": [1, 2, 3, 4]}])
    merged = birlestir({1: fast}, results=[heavy], requested={"docling": [1]},
                       score={fast: 100.0, f"garbled {FORMUL}": 10.0}.get, tolerans=5.0)

    assert merged.quarantined_pages == [1]
    assert merged.pages[0].text == fast
    assert merged.bolgeler == []


def test_the_fast_path_never_passes_an_html_marker_through():
    from research_platform.parsers.smart_router.merge import birlestir

    merged = birlestir({1: f"fast {GORSEL} text"})
    assert merged.pages[0].text == "fast [görsel] text"


def test_regions_reach_provenance():
    from research_platform.parsers.smart_pdf import SmartPdfParser
    from research_platform.parsers.smart_router.merge import birlestir

    heavy = _heavy({1: f"a {FORMUL} b"}, [{"tur": "formul", "page": 1, "bbox": [1, 2, 3, 4]}])
    merged = birlestir({1: "fast"}, results=[heavy], requested={"docling": [1]},
                       score=lambda t: 100.0)
    provenance = SmartPdfParser()._provenance({}, merged, 0.0, 0.0)
    assert provenance["bolgeler"] == [
        {"tur": "formul", "page": 1, "bbox": [1, 2, 3, 4], "sira": 1}]


def test_the_service_payload_carries_regions_and_an_old_one_does_not_break(
        monkeypatch, tmp_path):
    import httpx

    from research_platform.parsers.smart_router import engines

    pdf = tmp_path / "belge.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setenv(engines.URL_ENV, "http://docling:3941")
    bolge = {"tur": "formul", "page": 1, "bbox": [1, 2, 3, 4]}
    for payload, beklenen in (
        ({"pages": {"1": "x"}, "tables": [], "regions": [bolge]}, [bolge]),
        ({"pages": {"1": "x"}, "tables": []}, []),
    ):
        yanit = types.SimpleNamespace(raise_for_status=lambda: None,
                                      json=lambda payload=payload: payload)
        monkeypatch.setattr(httpx, "post", lambda *a, yanit=yanit, **k: yanit)
        sonuc = engines.HttpDoclingEngine()._istek(str(pdf), [(1, 1)])
        assert sonuc[0] == {1: "x"}
        assert sonuc[5] == beklenen
