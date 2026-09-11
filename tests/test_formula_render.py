"""
Printing formula readings in the reports (formula_render.py).

The Word promise is the one that matters most: with no readings, the quote paragraph is
exactly what it always was. With readings, the placeholder becomes a real equation, or
the crop of the page when the reading does not build, or stays when there is nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from research_platform.formula_render import (
    FormulaDisplay,
    add_quote,
    latex_to_omml,
    load_formula_displays,
    markdown_formulas,
    normalize,
)

FIKSTUR = Path(__file__).parent / "fixtures" / "formul_kirpintilari"
KIRPINTILAR = json.loads((FIKSTUR / "beklenen.json").read_text(encoding="utf-8"))["kirpintilar"]
ONAYLI = [k for k in KIRPINTILAR if k["tur"] == "formul"]
M_OMATH = "{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath"


def _stil(run):
    run.bold = False


@pytest.mark.parametrize("girdi, beklenen", [
    (r"t = ( \frac{2y}{g} ) ^ { 0.5 }", r"t = \left( \frac{2y}{g} \right) ^ { 0.5 }"),
    (r"\text{H}^+ \rightarrow \text{Na}^{+}", r"\text{H}^{\text{+}} \rightarrow \text{Na}^{\text{+}}"),
    (r"[ M L T ^ { - 2 } ]", r"[ M L T ^ { - 2 } ]"),                 # sign of a number: kept
    (r"\frac { \mathrm { c m o l _ { c } } } { 1 }", r"\frac { \mathrm{cmol _ { c }} } { 1 }"),
    (r"x = v . t \qquad \qquad ( 7 )", r"x = v . t \quad \left( 7 \right)"),
    (r"f ( x ) ) (", r"f ( x ) ) ("),                                 # unbalanced: untouched
])
def test_normalize(girdi, beklenen):
    assert normalize(girdi) == beklenen


def test_every_approved_reading_builds_into_an_equation():
    basarisiz = [k["dosya"] for k in ONAYLI if latex_to_omml(k["beklenen"]) is None]
    assert basarisiz == []
    assert latex_to_omml(r"\frac{a}{b") is None


def test_markdown_gets_inline_math_where_there_is_a_reading():
    metin = "equal to: [formül 1] and [formül 2]."
    gosterim = {1: FormulaDisplay(latex="x = v . t"), 2: FormulaDisplay(image=b"png")}
    assert markdown_formulas(metin, gosterim) == "equal to: $x = v . t$ and [formül 2]."
    assert markdown_formulas(metin, {}) == metin


def _paragraf():
    return Document().add_paragraph()


def test_without_readings_the_quote_paragraph_is_unchanged():
    eski, yeni = _paragraf(), _paragraf()
    _stil(eski.add_run("“is equal to: [formül 1] here” "))
    add_quote(yeni, "is equal to: [formül 1] here", {}, _stil)
    assert yeni._p.xml == eski._p.xml


def test_a_reading_becomes_an_equation_between_the_text_runs():
    paragraf = _paragraf()
    add_quote(paragraf, "is equal to: [formül 1] here", {1: FormulaDisplay("x = v . t")}, _stil)
    ogeler = [oge.tag.rsplit("}", 1)[1] for oge in paragraf._p]
    assert ogeler == ["r", "oMath", "r"]
    assert [r.text for r in paragraf.runs] == ["“is equal to: ", " here” "]


def test_the_crop_prints_when_the_reading_does_not_build_or_is_missing():
    goruntu = (FIKSTUR / ONAYLI[0]["dosya"]).read_bytes()
    paragraf = _paragraf()
    add_quote(paragraf, "a [formül 1] b [formül 2] c [formül 3]",
              {1: FormulaDisplay(r"\frac{a}{b", goruntu), 2: FormulaDisplay("", goruntu)}, _stil)
    assert paragraf._p.xml.count("<w:drawing>") == 2
    assert paragraf._p.find(M_OMATH) is None
    assert paragraf.runs[-1].text == " c [formül 3]” "


def test_a_single_formula_goes_in_as_an_equation_or_its_crop():
    from research_platform.formula_render import add_formula

    goruntu = (FIKSTUR / ONAYLI[0]["dosya"]).read_bytes()
    denklem, kirpinti, bos = _paragraf(), _paragraf(), _paragraf()
    assert add_formula(denklem, FormulaDisplay("x = v . t", goruntu)) is True
    assert add_formula(kirpinti, FormulaDisplay(r"\frac{a}{b", goruntu)) is True
    assert add_formula(bos, FormulaDisplay("(15.19)")) is False
    assert denklem._p.find(M_OMATH) is not None and "<w:drawing>" not in denklem._p.xml
    assert kirpinti._p.find(M_OMATH) is None and "<w:drawing>" in kirpinti._p.xml
    assert len(bos._p) == 0


def test_a_formula_too_wide_for_a_line_prints_as_its_crop_within_the_column():
    from docx.shared import Inches

    from research_platform.formula_render import (
        GENIS_FORMUL_KARAKTER,
        KIRPINTI_EN_GENIS_INC,
        add_formula,
        gorunur_uzunluk,
    )

    genis = next(k for k in ONAYLI if k["dosya"] == "01030000000165_1.png")
    assert gorunur_uzunluk(genis["beklenen"]) > GENIS_FORMUL_KARAKTER
    goruntu = (FIKSTUR / genis["dosya"]).read_bytes()

    kirpintili, kirpintisiz = _paragraf(), _paragraf()
    add_formula(kirpintili, FormulaDisplay(genis["beklenen"], goruntu))
    add_formula(kirpintisiz, FormulaDisplay(genis["beklenen"]))
    assert kirpintili._p.find(M_OMATH) is None
    (genislik,) = kirpintili._p.xpath(".//wp:extent/@cx")
    assert int(genislik) <= Inches(KIRPINTI_EN_GENIS_INC)
    assert kirpintisiz._p.find(M_OMATH) is not None      # nothing better to print


class _Depo:
    def __init__(self, satirlar):
        self.satirlar = satirlar
        self.cagri = 0

    async def list_formula_observations(self, source_version_ids):
        self.cagri += 1
        return [s for s in self.satirlar if s.source_version_id in source_version_ids]


class _NesneDeposu:
    async def get(self, key):
        return b"png:" + key.encode()


def _satir(no, latex, status="ok", model="qwen3.5:4b#formul1", surum="v1", anahtar="k"):
    return SimpleNamespace(source_version_id=surum, formula_no=no, latex=latex, status=status,
                           vision_model=model, image_key=anahtar)


AYAR = SimpleNamespace(formula_resolution_enabled=True, vision_model="qwen3.5:4b")
LINKLER = [SimpleNamespace(source_version_id="v1", quote="x is [formül 1] and [formül 2]"),
           SimpleNamespace(source_version_id="v2", quote="no formula here")]


async def test_nothing_is_loaded_when_formula_reading_is_off():
    depo = _Depo([_satir(1, "x")])
    kapali = SimpleNamespace(formula_resolution_enabled=False, vision_model="qwen3.5:4b")
    assert await load_formula_displays(repo=depo, store=_NesneDeposu(), links=LINKLER,
                                       settings=kapali) == {}
    assert await load_formula_displays(repo=depo, store=_NesneDeposu(), links=LINKLER,
                                       settings=None) == {}
    assert depo.cagri == 0


async def test_displays_follow_the_quotes_the_model_and_the_verdict():
    depo = _Depo([
        _satir(1, "x = old"),
        _satir(1, "x = v . t"),                                  # later reading wins
        _satir(2, "", status="reddedildi:matematik_isareti_yok"),  # crop only
        _satir(3, "y = 1"),                                      # not in any quote
        _satir(1, "z = 9", model="other-model#formul1"),         # another model's cache
    ])
    gosterim = await load_formula_displays(repo=depo, store=_NesneDeposu(), links=LINKLER,
                                           settings=AYAR)
    assert gosterim == {"v1": {1: FormulaDisplay("x = v . t", b"png:k"),
                               2: FormulaDisplay("", b"png:k")}}


async def test_formulas_of_the_evidence_passage_are_loaded_not_only_the_quote():
    depo = _Depo([_satir(1, "x = v . t"), _satir(3, "y = 1"), _satir(4, "z = 2")])
    link = SimpleNamespace(source_version_id="v1", quote="is equal to:",
                           location={"passage_id": "p1"})
    gosterim = await load_formula_displays(
        repo=depo, store=_NesneDeposu(), links=[link], settings=AYAR,
        passage_texts={"p1": "is equal to: [formül 1] and later [formül 3].", "p2": "[formül 4]"},
    )
    assert sorted(gosterim["v1"]) == [1, 3]


# --- the Word report ----------------------------------------------------------------

def _rapor(quote: str, displays, *, sentez: bool = True):
    import io

    from test_word_report import _minimal_report_inputs

    from research_platform.report_synthesis import (
        StudyProfile,
        SynthesisPackage,
        SynthesisSection,
    )
    from research_platform.word_report import build_word_report

    girdiler = _minimal_report_inputs()
    kanit = SimpleNamespace(quote=quote, source_version_id="v1")
    girdiler["evidence_by_claim"] = {"claim-1": [(kanit, girdiler["sources"][0])]}
    paket = SynthesisPackage(
        executive_summary="The outcome improved [S01].",
        sections=[SynthesisSection(title="Measured outcome",
                                   synthesis="The outcome improved in the study [S01].",
                                   consensus="One study [S01].", source_ids=["S01"],
                                   claim_ids=["claim-1"])],
        study_profiles=[StudyProfile(source_id="source-1", source_label="S01",
                                     title="Independent clinical source",
                                     contribution="Detection / diagnosis",
                                     evidence_design="Observational")],
        cross_study_assessment="One study [S01].", conclusion="Replicate [S01].",
        uncertainty="Single study [S01].", generated_by_llm=True,
    ) if sentez else None
    rapor = build_word_report(**girdiler, synthesis_package=paket, formula_displays=displays)
    return Document(io.BytesIO(rapor.document))


def _basliklar(belge) -> list[str]:
    return [p.text for p in belge.paragraphs if p.style.name.startswith("Heading")]


def test_the_synthesis_report_prints_read_formulas_in_appendix_f():
    belge = _rapor("The distance is [formül 1] in general.",
                   {"v1": {1: FormulaDisplay("x = v . t")}})
    assert "Appendix F. Formula reading register" in _basliklar(belge)
    hucreler = [c.text for t in belge.tables for r in t.rows for c in r.cells]
    assert "[formül 1]" in hucreler
    assert "oMath" in belge.element.xml


def test_the_appendix_lists_the_passage_formulas_even_when_the_quote_has_none():
    # The model quotes the sentence before a formula, not the formula (end-to-end run,
    # 2026-09-11); the loader supplies the passage's formulas, the report prints them.
    belge = _rapor("The distance is equal to:", {"v1": {1: FormulaDisplay("x = v . t"),
                                                       2: FormulaDisplay("y = g t^{2}")}})
    assert "Appendix F. Formula reading register" in _basliklar(belge)
    hucreler = [c.text for t in belge.tables for r in t.rows for c in r.cells]
    assert "[formül 1]" in hucreler and "[formül 2]" in hucreler


def test_no_readings_for_the_cited_sources_means_no_appendix_f():
    for quote, displays in (
        ("The distance is [formül 1] in general.", None),
        ("The distance is [formül 1] in general.", {}),
        ("The distance is [formül 1] in general.", {"v9": {1: FormulaDisplay("x = v . t")}}),
    ):
        belge = _rapor(quote, displays)
        assert not any(b.startswith("Appendix F") for b in _basliklar(belge))
        assert "oMath" not in belge.element.xml


def test_the_classic_report_prints_the_equation_inside_the_quote():
    belge = _rapor("The distance is [formül 1] in general.",
                   {"v1": {1: FormulaDisplay("x = v . t")}}, sentez=False)
    paragraf = next(p for p in belge.paragraphs if "The distance is" in p.text)
    assert "oMath" in paragraf._p.xml
    assert "[formül 1]" not in paragraf.text


@pytest.mark.skipif(shutil.which("soffice") is None or shutil.which("pdftotext") is None,
                    reason="needs LibreOffice and poppler to render the .docx")
def test_every_approved_reading_prints_whole_through_libreoffice(tmp_path):
    """
    One formula per page; every letter and digit of the reading must be on its page at
    least as often as in the reading. Scanning for "¿" alone passed while square roots
    printed empty (end-to-end render, 2026-09-11): a dropped radicand drops characters.
    """
    import re
    from collections import Counter

    from docx.enum.text import WD_BREAK

    from research_platform.formula_render import GENIS_FORMUL_KARAKTER, add_formula, gorunur_uzunluk

    # Too wide for a line: those print as the crop (see the test below), not as equations.
    dar = [k for k in ONAYLI if gorunur_uzunluk(k["beklenen"]) <= GENIS_FORMUL_KARAKTER]
    assert len(dar) >= 17
    belge = Document()
    for sira, kirpinti in enumerate(dar):
        paragraf = belge.add_paragraph()
        assert add_formula(paragraf, FormulaDisplay(kirpinti["beklenen"]))
        if sira < len(dar) - 1:
            paragraf.add_run().add_break(WD_BREAK.PAGE)
    yol = tmp_path / "formuller.docx"
    belge.save(yol)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path),
                    str(yol)], check=True, capture_output=True, timeout=180)
    pdf = tmp_path / "formuller.pdf"

    eksik = {}
    for sayfa, kirpinti in enumerate(dar, 1):
        basili = subprocess.run(["pdftotext", "-f", str(sayfa), "-l", str(sayfa), str(pdf), "-"],
                                check=True, capture_output=True, text=True).stdout
        beklenen = Counter(re.findall(r"[A-Za-z0-9]", re.sub(r"\\[A-Za-z]+", " ",
                                                               kirpinti["beklenen"])))
        fark = beklenen - Counter(re.findall(r"[A-Za-z0-9]", basili))
        if fark or "¿" in basili:
            eksik[kirpinti["dosya"]] = dict(fark)
    assert eksik == {}
