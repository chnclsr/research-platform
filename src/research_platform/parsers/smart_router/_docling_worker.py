"""
Runs Docling in a separate interpreter and reports page markdown as JSON.

Docling pulls in torch and is several gigabytes installed, so it is an optional
dependency rather than something every deployment carries. When it is not
importable in the running interpreter, engines.py starts this module under an
interpreter that does have it and reads the result off stdout.

Running Docling out of process buys one thing threads cannot: a timeout that
actually stops the work. A thread that overruns keeps holding its memory and GPU
until it finishes on its own; a process can be killed.

Called as:  python -m ..._docling_worker <pdf_path> <blocks_json>
where blocks_json is [[first_page, last_page], ...], 1-based and inclusive.
Only the JSON object on the last stdout line is part of the contract; Docling
writes progress output of its own above it.
"""

from __future__ import annotations

import json
import os
import sys

# torch.compile shells out to a C++ compiler that is not present on a stock
# Windows box, and its absence takes the whole conversion down.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")


def _table_grid(table) -> dict | None:
    """
    Flatten one Docling table into headers and rows.

    Docling exposes a cell grid with row/column indices and a column_header flag,
    which is more than the markdown rendering keeps: once a table is prose, which
    number belonged to which column is gone. ParsedTable is where that survives.
    """
    grid = getattr(table.data, "grid", None)
    if not grid:
        return None
    matrix = [[(cell.text or "").strip() for cell in row] for row in grid]
    if not matrix:
        return None

    # Leading rows Docling marked as column headers; the rest is body.
    header_depth = 0
    for row in grid:
        if any(getattr(cell, "column_header", False) for cell in row):
            header_depth += 1
        else:
            break

    page_no = table.prov[0].page_no if getattr(table, "prov", None) else None
    return {
        "page": page_no,
        "headers": matrix[0] if header_depth else [],
        "rows": matrix[header_depth:] if header_depth else matrix,
    }


def sayfa_markdown(document, page_no: int) -> str:
    """
    One page of a converted document as markdown, the way every Docling path renders it.

    `escape_html=False` because the default HTML-escapes body text: "pH < 5.8" reached
    passages as "pH &lt; 5.8", in 68 of 114 live PDFs, and nothing downstream unescapes
    it. Measured 2026-09-11 on 12 PDFs: the unescaped output equals `html.unescape` of
    the escaped one, byte for byte -- the entities are the only difference. Code and
    formula items were never escaped by Docling in the first place.

    The service, the bridged worker and the in-process path all call this, so the three
    cannot drift apart: they produce content_hash-bearing text for the same document.
    """
    return document.export_to_markdown(page_no=page_no, escape_html=False)


#: A picture smaller than this on both sides, in PDF points, is an icon or a bullet glyph
#: rather than content. Measured 2026-09-11: 01030000000165 carries two 20x20 pt pictures
#: with no caption and nothing a reader would call a figure. merge.py drops their marker
#: instead of numbering it, so "[görsel N]" only ever points at something worth a look.
IKON_KENAR_PT = 40.0


def sayfa_bolgeleri(document, page_no: int) -> list[dict]:
    """
    Where the undecoded formulas and the pictures on one page are, in the order
    `sayfa_markdown` prints their markers.

    Docling's layout model finds a formula even with formula enrichment off -- it has
    the box, it just does not read it -- and the serializer prints
    `<!-- formula-not-decoded -->` for exactly those items (empty text, non-empty
    orig), `<!-- image -->` for each picture. merge.py maps the n-th marker of a kind on
    a page to the n-th region of that kind, which is only sound if this walks the same
    items in the same order as the serializer: body layer, document order. A decoded
    formula is already LaTeX in the text and has no marker, so it is not listed.

    Boxes are in PDF points with a top-left origin, the convention PyMuPDF crops with.
    Duck-typed on purpose: the platform image imports this module without docling.
    """
    try:
        from docling_core.types.doc import ContentLayer

        katmanlar = {ContentLayer.BODY}
    except Exception:  # pragma: no cover - only absent where docling is absent
        katmanlar = None
    sayfa = (getattr(document, "pages", None) or {}).get(page_no)
    yukseklik = float(getattr(getattr(sayfa, "size", None), "height", 0.0) or 0.0)

    bolgeler: list[dict] = []
    for item, _level in document.iterate_items(page_no=page_no,
                                               included_content_layers=katmanlar):
        etiket = getattr(item, "label", "")
        etiket = str(getattr(etiket, "value", etiket))
        if etiket == "formula":
            if getattr(item, "text", "") or not getattr(item, "orig", ""):
                continue
            tur = "formul"
        elif etiket in ("picture", "chart"):
            tur = "gorsel"
        else:
            continue
        prov = next((p for p in getattr(item, "prov", None) or [] if p.page_no == page_no),
                    None)
        if prov is None:
            continue
        kutu = prov.bbox.to_top_left_origin(page_height=yukseklik)
        sol, ust, sag, alt = kutu.l, kutu.t, kutu.r, kutu.b
        bolge = {"tur": tur, "page": page_no,
                 "bbox": [round(float(v), 1) for v in (sol, ust, sag, alt)]}
        if tur == "gorsel":
            try:
                baslik = item.caption_text(document) or ""
            except Exception:
                baslik = ""
            bolge["caption"] = " ".join(str(baslik).split())[:300]
            bolge["ikon"] = (sag - sol) < IKON_KENAR_PT and (alt - ust) < IKON_KENAR_PT
        bolgeler.append(bolge)
    return bolgeler


def cihaz() -> str:
    """Which accelerator Docling actually resolved to -- asked, not guessed.

    Measured on an RTX 4060 box: the same PDF, same Docling build, produces
    DIFFERENT text on CPU and on CUDA -- 4 of 9 documents in the corpus, one of
    them losing an entire markdown table. `content_hash` is the sha256 of that
    text and dedup, snapshot keys and passage offsets all hang off it, so the
    device is part of the contract and has to reach provenance. Two workers on
    different accelerators are not interchangeable.

    Docling's own resolver is the source: AUTO picks CUDA when torch sees it,
    and inferring that from `torch.cuda.is_available()` here would guess at a
    decision Docling has already made.
    """
    try:
        from docling.datamodel.pipeline_options import AcceleratorDevice
        from docling.utils.accelerator_utils import decide_device

        return str(decide_device(AcceleratorDevice.AUTO.value))
    except Exception as exc:  # pragma: no cover - depends on the docling build
        return f"bilinmiyor ({type(exc).__name__})"


def yapi() -> str:
    """Docling + torch + accelerator, as one string for provenance.

    The device alone does not pin the output -- a docling upgrade changes the text on
    the same card -- so `cihaz()`'s answer travels with the versions that produced it.
    Read from installation metadata: docling exports no `__version__`.
    """
    import importlib.metadata as _metadata

    parcalar = []
    for paket in ("docling", "torch"):
        try:
            parcalar.append(f"{paket} {_metadata.version(paket)}")
        except Exception:
            parcalar.append(f"{paket} bilinmiyor")
    parcalar.append(cihaz())
    return ", ".join(parcalar)


def run(pdf_path: str, blocks: list[list[int]]) -> dict:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    pages: dict[int, str] = {}
    tables: list[dict] = []
    regions: list[dict] = []
    for first, last in blocks:
        # Consecutive pages go in one call: the same 12 pages cost 18.56s grouped
        # against 29.28s one call at a time.
        result = converter.convert(pdf_path, page_range=(first, last))
        for page_no in range(first, last + 1):
            try:
                pages[page_no] = sayfa_markdown(result.document, page_no)
            except Exception as exc:
                # One unreadable page should not cost us the rest of the block.
                pages[page_no] = ""
                print(f"page {page_no} failed: {exc}", file=sys.stderr)
            try:
                regions.extend(sayfa_bolgeleri(result.document, page_no))
            except Exception as exc:
                # Without regions the page still merges; its markers just stay
                # unnumbered (merge.py). Not worth losing the text over.
                print(f"regions for page {page_no} skipped: {exc}", file=sys.stderr)
        for table in getattr(result.document, "tables", None) or []:
            try:
                flattened = _table_grid(table)
            except Exception as exc:
                print(f"table skipped: {exc}", file=sys.stderr)
                continue
            if flattened:
                tables.append(flattened)
    return {"pages": pages, "tables": tables, "regions": regions,
            "device": cihaz(), "build": yapi()}


def main(argv: list[str]) -> int:
    # Windows hands us the console codepage (cp1254 on a Turkish box), which
    # cannot encode much of what Docling extracts -- a single superscript is
    # enough to kill the run after the conversion has already been paid for.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if len(argv) < 3:
        print(json.dumps({"error": "usage: _docling_worker <pdf> <blocks_json>"}))
        return 2
    try:
        payload = run(argv[1], json.loads(argv[2]))
    except Exception as exc:
        payload = {"error": f"{type(exc).__name__}: {exc}"}
    # The marker lets the caller find our line among Docling's own chatter.
    print("__SMART_ROUTER_RESULT__" + json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
