from __future__ import annotations

from types import SimpleNamespace

import pytest

from research_platform.parsers.smart_pdf import SmartPdfParser
from research_platform.parsers.smart_router.engines import EngineResult
from research_platform.parsers.smart_router.gate import GirisKapisi
from research_platform.parsers.smart_router.inspector import (
    PROFIL_INSPECTOR,
    InspectorSayfa,
    InspectorSonuc,
)
from research_platform.parsers.smart_router.lexical import (
    LEXICAL_NORMALIZER_VERSION,
    build_lexical_reference,
    expand_ligatures,
    repair_ligatures,
)
from research_platform.parsers.smart_router.merge import (
    MergedDocument,
    MergedPage,
    sayfa_basliklariyla,
)
from research_platform.passages import chunk_document


def test_expand_ligatures_covers_unicode_presentation_forms():
    assert expand_ligatures("\ufb00 \ufb01 \ufb02 \ufb03 \ufb04 \ufb05 \ufb06") == (
        "ff fi fl ffi ffl st st"
    )


def test_repairs_source_backed_single_and_split_fi_fl_losses():
    source = "Arti\ufb01cial intelligence is signi\ufb01cantly changing \ufb01nancial work\ufb02ows."
    parsed = "Arti cial intelligence is signicantly changing nancial workows."

    result = repair_ligatures(parsed, build_lexical_reference(source))

    assert result.text == (
        "Artificial intelligence is significantly changing financial workflows."
    )
    assert result.repairs == 4
    assert result.split_token == 1
    assert result.single_token == 3
    assert result.ambiguous == 0


def test_does_not_guess_when_source_uses_plain_ascii_fi_fl():
    reference = build_lexical_reference("Artificial financial workflows")
    parsed = "Arti cial nancial workows"

    result = repair_ligatures(parsed, reference)

    assert result.text == parsed
    assert result.repairs == 0


def test_correct_parser_output_is_unchanged_and_second_pass_is_idempotent():
    reference = build_lexical_reference("prede\ufb01ned work\ufb02ow")
    first = repair_ligatures("predefined workflow", reference)
    repaired = repair_ligatures("predened workow", reference)
    second = repair_ligatures(repaired.text, reference)

    assert first.repairs == 0
    assert repaired.text == "predefined workflow"
    assert repaired.repairs == 2
    assert second.text == repaired.text
    assert second.repairs == 0


def test_split_repair_handles_soft_wrap_but_not_a_blank_line():
    reference = build_lexical_reference("classi\ufb01-\ncation Artificial")

    soft_wrap = repair_ligatures("classica- tion", reference)
    blank_line = repair_ligatures("Arti\n\ncial", reference)

    assert soft_wrap.text == "classification"
    assert soft_wrap.repairs == 1
    assert blank_line.text == "Arti\n\ncial"
    assert blank_line.repairs == 0


def test_legitimate_source_word_pair_is_not_joined():
    reference = build_lexical_reference("Arti cial and Arti\ufb01cial are distinct.")

    result = repair_ligatures("Arti cial", reference)

    assert result.text == "Arti cial"
    assert result.repairs == 0


def test_split_is_not_joined_when_its_skeleton_is_a_real_source_word():
    reference = build_lexical_reference("articial and Arti\ufb01cial")

    result = repair_ligatures("Arti cial", reference)

    assert result.text == "Arti cial"
    assert result.repairs == 0


def test_line_wrapped_fragment_is_not_rewritten_into_another_page_word():
    """A fragment the source knows only as half of a wrapped word stays a fragment.

    `termi- nal` is correct parser output; the source joins it into `terminal`, so
    the fragment is missing from the reference for that reason alone. Rewriting it
    into the page's other `nal` candidate would corrupt already-correct text.
    """
    reference = build_lexical_reference("the \ufb01nal termi-\nnal state")

    already_correct = repair_ligatures("the final termi- nal state", reference)
    with_a_real_loss = repair_ligatures(
        "the nal result and the termi- nal state", reference,
    )

    assert already_correct.text == "the final termi- nal state"
    assert already_correct.repairs == 0
    assert with_a_real_loss.text == "the final result and the termi- nal state"
    assert with_a_real_loss.repairs == 1


def test_split_repair_joins_a_plain_line_break():
    reference = build_lexical_reference("Arti\ufb01cial systems")

    result = repair_ligatures("Arti\ncial systems", reference)

    assert result.text == "Artificial systems"
    assert result.split_token == 1


def test_repair_follows_the_case_of_the_parser_token():
    reference = build_lexical_reference("prede\ufb01ned Arti\ufb01cial")

    assert repair_ligatures("PREDENED", reference).text == "PREDEFINED"
    assert repair_ligatures("ARTI CIAL", reference).text == "ARTIFICIAL"


def test_a_page_that_raises_leaves_every_other_page_untouched(monkeypatch):
    import research_platform.parsers.smart_pdf as smart_pdf_module

    merged = MergedDocument(pages=[
        MergedPage(page_no=1, text="predened", engine="pdf-inspector"),
        MergedPage(page_no=2, text="workow", engine="docling"),
    ])
    real = smart_pdf_module.repair_ligatures

    def raises_on_the_second_page(text, reference):
        if text == "workow":
            raise RuntimeError("synthetic failure")
        return real(text, reference)

    monkeypatch.setattr(
        smart_pdf_module, "repair_ligatures", raises_on_the_second_page,
    )

    with pytest.raises(RuntimeError):
        SmartPdfParser()._normalize_ligatures(
            merged, {1: "prede\ufb01ned", 2: "work\ufb02ow"},
        )

    assert merged.pages[0].text == "predened"
    assert merged.pages[1].text == "workow"


def test_ambiguous_page_local_candidates_are_left_unchanged():
    reference = build_lexical_reference("\ufb01nal and \ufb02nal")

    result = repair_ligatures("nal", reference)

    assert result.text == "nal"
    assert result.repairs == 0
    assert result.ambiguous == 1


def test_gate_reuses_its_existing_text_extraction(monkeypatch):
    calls: list[tuple] = []

    class FakePage:
        rect = SimpleNamespace(width=600.0, height=800.0)

        def get_text(self, *args, **kwargs):
            calls.append((args, kwargs))
            return [] if args == ("words",) else "prede\ufb01ned body"

        def get_images(self, *, full):
            assert full is True
            return []

        def get_drawings(self):
            return []

        def cluster_drawings(self):
            return []

    class FakeDocument:
        def __iter__(self):
            return iter([FakePage()])

        def close(self):
            return None

    from research_platform.parsers.smart_router import gate as gate_module

    monkeypatch.setattr(gate_module.pymupdf, "open", lambda _: FakeDocument())
    inspector = InspectorSonuc(
        pdf_path="fixture.pdf",
        profil=PROFIL_INSPECTOR,
        pages=[InspectorSayfa(sayfa_no=1, markdown="predened body")],
    )
    source_text: dict[int, str] = {}

    GirisKapisi().bayrakla(
        "fixture.pdf", insp=inspector, source_text_by_page=source_text,
    )

    assert source_text == {1: "prede\ufb01ned body"}
    assert calls == [((), {}), (("words",), {})]


def test_smart_parser_normalization_preserves_page_and_passage_contracts():
    parser = SmartPdfParser()
    merged = MergedDocument(pages=[
        MergedPage(
            page_no=1,
            text="predened " + "first-page evidence " * 20,
            engine="pdf-inspector",
        ),
        MergedPage(
            page_no=2,
            text="Arti cial " + "second-page evidence " * 20,
            engine="docling",
        ),
    ])
    sources = {
        1: "prede\ufb01ned " + "first-page evidence " * 20,
        2: "Arti\ufb01cial " + "second-page evidence " * 20,
    }

    summary = parser._normalize_ligatures(merged, sources)
    content = sayfa_basliklariyla(merged)
    passages = chunk_document(content, "lexical-test", target_tokens=30, overlap_tokens=5)
    provenance = parser._provenance(
        {"parser_profile": PROFIL_INSPECTOR, "lexical_normalization": summary},
        merged, 0.0, 0.0,
    )

    assert "predefined" in merged.pages[0].text
    assert "Artificial" in merged.pages[1].text
    assert summary == {
        "version": LEXICAL_NORMALIZER_VERSION,
        "applied": True,
        "referenced_pages": 2,
        "repairs": 2,
        "single_token": 1,
        "split_token": 1,
        "ambiguous": 0,
        "changed_pages": [1, 2],
        "repairs_by_engine": {"pdf-inspector": 1, "docling": 1},
    }
    assert passages
    assert {passage.page_number for passage in passages} == {1, 2}
    assert all(content[p.start_char:p.end_char].strip() == p.text for p in passages)
    assert provenance["lexical_normalization"] == summary


def test_missing_source_page_fails_closed_without_touching_text():
    merged = MergedDocument(pages=[
        MergedPage(page_no=1, text="predened", engine="pdf-inspector"),
    ])

    summary = SmartPdfParser()._normalize_ligatures(merged, {})

    assert merged.pages[0].text == "predened"
    assert summary["referenced_pages"] == 0
    assert summary["repairs"] == 0


def test_full_smart_parser_path_repairs_fast_and_heavy_winners(monkeypatch):
    import research_platform.parsers.smart_pdf as smart_pdf_module

    body = "evidence text " * 30

    class FakeRouter:
        def calistir(self, path, *, metin_dahil):
            assert metin_dahil is True
            return {
                "parser_profile": PROFIL_INSPECTOR,
                "sayfa_metni": {1: "predened " + body, 2: "fast fallback " + body},
                "_source_text_by_page": {
                    1: "prede\ufb01ned " + body,
                    2: "Arti\ufb01cial " + body,
                },
                "sayfalar": [
                    {"sayfa_no": 1, "karar_kaynagi": []},
                    {"sayfa_no": 2, "karar_kaynagi": ["has_table_yuksek"]},
                ],
            }

    class FakeDocling:
        name = "docling"

        def available(self):
            return True, "test double"

        def extract(self, path, pages):
            assert pages == [2]
            return EngineResult(
                engine=self.name, pages={2: "Arti cial " + body}, device="cpu",
            )

    monkeypatch.setattr(smart_pdf_module, "SmartRouterHatti", FakeRouter)
    monkeypatch.setattr(smart_pdf_module, "DoclingEngine", FakeDocling)

    parsed = SmartPdfParser().parse(b"%PDF lexical fixture", url="https://example.org/a.pdf")
    lexical = parsed.parse_provenance["lexical_normalization"]

    assert "predefined" in parsed.text
    assert "Artificial" in parsed.text
    assert parsed.page_count == 2
    assert lexical["repairs"] == 2
    assert lexical["repairs_by_engine"] == {"pdf-inspector": 1, "docling": 1}
    assert lexical["changed_pages"] == [1, 2]
    assert "_source_text_by_page" not in parsed.parse_provenance
    passages = chunk_document(parsed.text, "full-path", target_tokens=30, overlap_tokens=5)
    assert {passage.page_number for passage in passages} == {1, 2}


def test_full_parser_keeps_selected_text_if_normalizer_itself_fails(monkeypatch):
    import research_platform.parsers.smart_pdf as smart_pdf_module

    class FakeRouter:
        def calistir(self, path, *, metin_dahil):
            return {
                "parser_profile": PROFIL_INSPECTOR,
                "sayfa_metni": {1: "usable selected text"},
                "_source_text_by_page": {1: "source text"},
                "sayfalar": [{"sayfa_no": 1, "karar_kaynagi": []}],
            }

    monkeypatch.setattr(smart_pdf_module, "SmartRouterHatti", FakeRouter)
    monkeypatch.setattr(
        smart_pdf_module, "build_lexical_reference",
        lambda text: (_ for _ in ()).throw(RuntimeError("synthetic failure")),
    )

    parsed = SmartPdfParser().parse(b"%PDF lexical fixture", url="https://example.org/a.pdf")

    assert "usable selected text" in parsed.text
    assert parsed.parse_provenance["lexical_normalization"] == {
        "version": LEXICAL_NORMALIZER_VERSION,
        "applied": False,
        "error": "RuntimeError: synthetic failure",
        "repairs": 0,
    }
