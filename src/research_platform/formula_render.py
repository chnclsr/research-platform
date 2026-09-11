"""
Printing "[formül N]" placeholders in the reports a person reads.

The text keeps the placeholder -- passages, quotes and content_hash all carry it. What a
report shows in its place is the vision model's reading from formula_observations
(formula_resolution.py): a real equation in the Word report, as OMML -- the format
Word's own equation editor writes, fractions and roots included, not LaTeX source --
and `$...$` in the markdown report. When a reading cannot be built into an equation,
the Word report shows the crop of the original page instead; with nothing at all, the
placeholder stays. A reader always sees either the formula or an honest gap.

Measured 2026-09-11 on the 24 readings in tests/fixtures/formul_kirpintilari:
latex2mathml -> mathml2omml built all 24, and with the normalisations below every one
printed cleanly when the .docx was rendered by LibreOffice. Without them `( ... )^{0.5}`
hung the exponent on the closing parenthesis and `H^{+}` printed as "+¿".
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .formula_resolution import FORMUL_YER_TUTUCU, ONBELLEK_SURUMU, red_nedeni

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

#: A superscript or subscript that is nothing but a sign: `^+`, `^{+}`, `_ { - }`.
#: Not `^{-2}` -- there the sign belongs to a number and the group is left alone.
_YALNIZ_ISARET_INDIS = re.compile(r"([\^_])\s*(?:\{\s*([+\-])\s*\}|([+\-])(?![\w{\\]))")
_MATHRM = re.compile(r"\\mathrm\s*\{")


@dataclass(frozen=True)
class FormulaDisplay:
    """What a report can show for one placeholder: the reading, the crop, or both."""

    latex: str = ""
    image: bytes = b""


def _mathrm_birlestir(latex: str) -> str:
    """`\\mathrm { c m o l }` -> `\\mathrm{cmol}`: models space letters out token by token,
    and inside \\mathrm those spaces are printed, so "cmol" read as "c m o l"."""
    parcalar: list[str] = []
    i = 0
    while (eslesme := _MATHRM.search(latex, i)) is not None:
        parcalar.append(latex[i:eslesme.start()])
        j, derinlik = eslesme.end(), 1
        while j < len(latex) and derinlik:
            derinlik += {"{": 1, "}": -1}.get(latex[j], 0)
            j += 1
        ic = latex[eslesme.end():j - 1] if derinlik == 0 else latex[eslesme.end():j]
        ic = re.sub(r"(?<=[A-Za-z])\s+(?=[A-Za-z])", "", ic).strip()
        parcalar.append("\\mathrm{" + ic + ("}" if derinlik == 0 else ""))
        i = j
    parcalar.append(latex[i:])
    return "".join(parcalar)


def _parantez_grupla(latex: str) -> str:
    """Bare `( ... )` -> `\\left( ... \\right)`: latex2mathml otherwise attaches a following
    exponent to the closing parenthesis alone. Left untouched unless balanced."""
    if "\\left(" in latex or latex.count("(") != latex.count(")"):
        return latex
    derinlik = 0
    for karakter in latex:
        derinlik += {"(": 1, ")": -1}.get(karakter, 0)
        if derinlik < 0:
            return latex
    latex = re.sub(r"(?<!\\right)\)", r"\\right)", latex)
    return re.sub(r"(?<!\\left)\(", r"\\left(", latex)


def normalize(latex: str) -> str:
    """Rewrite a reading so it builds into an equation that prints; content unchanged."""
    latex = re.sub(r"(\\q?quad\s*)+", r"\\quad ", (latex or "").strip())
    latex = _mathrm_birlestir(latex)
    latex = _parantez_grupla(latex)
    return _YALNIZ_ISARET_INDIS.sub(
        lambda m: f"{m.group(1)}{{\\text{{{m.group(2) or m.group(3)}}}}}", latex
    )


#: A square root as mathml2omml 0.0.2 writes it: `<m:rad><m:e>`, no degree. The OMML
#: schema requires `<m:deg>`; LibreOffice took the radicand for the degree and printed an
#: empty root, shifting everything after it (end-to-end render, 2026-09-11 -- the "¿"
#: scan missed it). Word writes a square root with the degree present and hidden.
_DERECESIZ_KOK = re.compile(r"<m:rad>(?!<m:radPr>|<m:deg)")


def _omml_onar(xml: str) -> str:
    return _DERECESIZ_KOK.sub('<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/>', xml)


def latex_to_omml(latex: str) -> Any | None:
    """An OMML element python-docx can append to a paragraph, or None when the reading
    cannot be built into one. The converters are imported here, not at module level: a
    worker image built without them still renders the report, with crops instead.

    A reading the resolver would not accept is not built either: latex2mathml closes an
    unbalanced `\\frac{a}{b` on its own, and would print a formula nobody read."""
    if red_nedeni(latex) is not None:
        return None
    try:
        import latex2mathml.converter
        import mathml2omml
        from docx.oxml import parse_xml
    except ImportError:
        return None
    try:
        xml = _omml_onar(mathml2omml.convert(latex2mathml.converter.convert(normalize(latex))))
        if not xml.startswith("<m:oMath>"):
            return None
        return parse_xml(xml.replace("<m:oMath>", f'<m:oMath xmlns:m="{M_NS}">', 1))
    except Exception:  # noqa: BLE001 - any failure falls back to the crop
        return None


def markdown_formulas(text: str, displays: Mapping[int, FormulaDisplay]) -> str:
    """`[formül N]` -> `$LaTeX$` where there is a reading; the placeholder otherwise."""
    if not displays:
        return text

    def degistir(eslesme: re.Match) -> str:
        gosterim = displays.get(int(eslesme.group(1)))
        return f"${gosterim.latex}$" if gosterim and gosterim.latex else eslesme.group(0)

    return FORMUL_YER_TUTUCU.sub(degistir, text)


#: Visible characters (commands, grouping and spaces stripped, `gorunur_uzunluk`) beyond
#: which an equation no longer fits a report line. LibreOffice turns an OMML equation into
#: a formula object that cannot wrap and clips it at the margin: 01030000000165 #1 (83)
#: lost its last "NaOH", while 166 (63) and 165 #2 (60) printed whole and every other
#: reading of the 24 is 22 or shorter. 72 sits in the middle of that gap. Word can break
#: an inline equation at operators, but a report must read the same wherever it is
#: opened, so a wide formula prints as the crop of the page, which scales to the width.
GENIS_FORMUL_KARAKTER = 72
#: Widest a crop may print, in inches: inside the 4.9 in formula column of Appendix F.
KIRPINTI_EN_GENIS_INC = 4.6


def gorunur_uzunluk(latex: str) -> int:
    """Roughly how many characters a reading prints, to tell a wide formula apart."""
    return len(re.sub(r"\\[A-Za-z]+|[\s{}^_~\\]", "", latex or ""))


def _ogesi(gosterim: FormulaDisplay | None) -> Any | bytes | None:
    """The equation for a display, else its crop, else None -- the crop first when the
    formula is too wide for a line."""
    if gosterim is None:
        return None
    if gosterim.image and gorunur_uzunluk(gosterim.latex) > GENIS_FORMUL_KARAKTER:
        return gosterim.image
    denklem = latex_to_omml(gosterim.latex) if gosterim.latex else None
    if denklem is not None:
        return denklem
    return gosterim.image or None


def _ekle(paragraph: Any, oge: Any, image_height_pt: float) -> None:
    if isinstance(oge, bytes):
        from docx.shared import Inches, Pt

        resim = paragraph.add_run().add_picture(io.BytesIO(oge), height=Pt(image_height_pt))
        en_genis = Inches(KIRPINTI_EN_GENIS_INC)
        if resim.width > en_genis:
            resim.height = int(resim.height * en_genis / resim.width)
            resim.width = en_genis
    else:
        paragraph._p.append(oge)


def add_formula(paragraph: Any, display: FormulaDisplay, *,
                image_height_pt: float = 18.0) -> bool:
    """Append one formula to a paragraph -- equation, else crop. False when neither."""
    oge = _ogesi(display)
    if oge is None:
        return False
    _ekle(paragraph, oge, image_height_pt)
    return True


def add_quote(
    paragraph: Any, quote: str, displays: Mapping[int, FormulaDisplay],
    style: Callable[[Any], None], *, image_height_pt: float = 14.0,
) -> None:
    """
    Append `“quote” ` to a Word paragraph, each resolvable placeholder printed as an
    equation -- or as the crop when the reading does not build. Text runs go through
    `style`. With nothing to resolve this is exactly the single run the report always
    wrote, so a report without formula readings does not change by a byte.
    """
    parcalar = FORMUL_YER_TUTUCU.split(quote)
    numaralar = [int(n) for n in parcalar[1::2]]
    if not any(
        n in displays and (displays[n].latex or displays[n].image) for n in numaralar
    ):
        style(paragraph.add_run(f"“{quote}” "))
        return

    tampon = "“"
    for sira, parca in enumerate(parcalar):
        if sira % 2 == 0:
            tampon += parca
            continue
        oge = _ogesi(displays.get(int(parca)))
        if oge is None:
            tampon += f"[formül {parca}]"
            continue
        if tampon:
            style(paragraph.add_run(tampon))
            tampon = ""
        _ekle(paragraph, oge, image_height_pt)
    style(paragraph.add_run(tampon + "” "))


async def load_formula_displays(
    *, repo: Any, store: Any, links: Iterable[Any], settings: Any,
    passage_texts: Mapping[str, str] | None = None,
) -> dict[str, dict[int, FormulaDisplay]]:
    """
    source_version_id -> formula number -> what to print, for the formulas behind the
    report's evidence: those in each quote, and those in the passage the quote came from.

    The passage matters more than the quote. Measured end to end on 2026-09-11: given
    the readings, the model wrote "… is equal to: x = v . t" as the claim, but quoted
    only "… is equal to:" -- the sentence stops where the formula starts, so a quote
    rarely carries its placeholder. `passage_texts` is passage id -> text, matched
    through each link's location["passage_id"].

    Off unless FORMULA_RESOLUTION_ENABLED, and then the database is not touched
    (migration 0011 may not have run).
    """
    if settings is None or not getattr(settings, "formula_resolution_enabled", False):
        return {}
    passage_texts = passage_texts or {}
    istenen: dict[str, set[int]] = {}
    for link in links:
        passage_id = str((getattr(link, "location", None) or {}).get("passage_id") or "")
        metin = (getattr(link, "quote", "") or "") + " " + passage_texts.get(passage_id, "")
        numaralar = FORMUL_YER_TUTUCU.findall(metin)
        if numaralar:
            istenen.setdefault(str(link.source_version_id), set()).update(
                int(n) for n in numaralar
            )
    if not istenen:
        return {}

    cache_model = f"{settings.vision_model}#{ONBELLEK_SURUMU}"
    gosterimler: dict[str, dict[int, FormulaDisplay]] = {}
    # Ordered oldest first, so a later reading of the same placeholder wins.
    for satir in await repo.list_formula_observations(list(istenen)):
        if satir.vision_model != cache_model:
            continue
        if satir.formula_no not in istenen.get(satir.source_version_id, set()):
            continue
        goruntu = b""
        if satir.image_key:
            try:
                goruntu = await store.get(satir.image_key)
            except Exception:  # noqa: BLE001 - the reading alone still prints
                goruntu = b""
        latex = satir.latex if satir.status == "ok" else ""
        if latex or goruntu:
            gosterimler.setdefault(satir.source_version_id, {})[satir.formula_no] = (
                FormulaDisplay(latex=latex, image=goruntu)
            )
    return gosterimler
