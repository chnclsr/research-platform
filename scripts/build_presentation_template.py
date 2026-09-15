"""Build the base deck the PowerPoint report is drawn on.

The report renderer (`research_platform.presentation_report`) draws every slide itself from
measured geometry, so the base deck carries only what code cannot recreate: the 16:9 page
and the theme of the corporate v1 template. This script derives it from v1 by removing every
slide, every layout but one blank layout, and the embedded fonts, and by making Arial the
theme font so text typed into the deck by hand matches the generated text.

The embedded faces are dropped because PowerPoint does not recognise them: the Google Slides
export stored Roboto in a form PowerPoint reports as not embedded, so a viewer without Roboto
installed saw a substitute font and every measured line broke differently.

    .venv\\Scripts\\python.exe scripts\\build_presentation_template.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pptx
from pptx.oxml.ns import qn

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "research_platform" / "templates"
SOURCE = TEMPLATES / "Cansagligi_Arastirma_Raporu_Sablonu_v1.pptx"
TARGET = TEMPLATES / "Cansagligi_Arastirma_Raporu_Sablonu_v2.pptx"
KEEP_LAYOUT = "OBJECT"
THEME_FONT = "Arial"


def build(source: Path, target: Path) -> None:
    prs = pptx.Presentation(str(source))

    slide_ids = prs.slides._sldIdLst
    for slide_id in list(slide_ids):
        prs.part.drop_rel(slide_id.rId)
        slide_ids.remove(slide_id)

    master = prs.slide_master
    for layout in list(master.slide_layouts):
        if layout.name != KEEP_LAYOUT:
            master.slide_layouts.remove(layout)
    layout = master.slide_layouts.get_by_name(KEEP_LAYOUT)
    if layout is None:
        raise SystemExit(f"layout {KEEP_LAYOUT!r} not found in {source}")
    layout.name = "Rapor"
    for shape in list(layout.placeholders):
        shape._element.getparent().remove(shape._element)

    embedded = prs.part._element.find(qn("p:embeddedFontLst"))
    if embedded is not None:
        for font in list(embedded):
            for style in font:
                rid = style.get(qn("r:id"))
                if rid:
                    prs.part.drop_rel(rid)
            embedded.remove(font)
        prs.part._element.remove(embedded)

    theme_part = next(
        rel.target_part for rel in master.part.rels.values() if rel.reltype.endswith("/theme")
    )
    theme = theme_part._element if hasattr(theme_part, "_element") else None
    if theme is None:
        from lxml import etree

        theme = etree.fromstring(theme_part.blob)
        for tag in ("a:majorFont", "a:minorFont"):
            latin = theme.find(f".//{qn(tag)}/{qn('a:latin')}")
            if latin is not None:
                latin.set("typeface", THEME_FONT)
        theme_part._blob = etree.tostring(theme, xml_declaration=True, encoding="UTF-8", standalone=True)
    else:
        for tag in ("a:majorFont", "a:minorFont"):
            latin = theme.find(f".//{qn(tag)}/{qn('a:latin')}")
            if latin is not None:
                latin.set("typeface", THEME_FONT)

    # The master's own text styles still name the export's fonts (Calibri).
    for latin in master._element.iter(qn("a:latin")):
        typeface = latin.get("typeface") or ""
        if typeface and not typeface.startswith("+") and typeface != THEME_FONT:
            latin.set("typeface", THEME_FONT)

    prs.save(str(target))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--target", type=Path, default=TARGET)
    args = parser.parse_args()
    build(args.source, args.target)
    print(f"wrote {args.target}")


if __name__ == "__main__":
    main()
