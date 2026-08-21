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


def run(pdf_path: str, blocks: list[list[int]]) -> dict:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    pages: dict[int, str] = {}
    tables: list[dict] = []
    for first, last in blocks:
        # Consecutive pages go in one call: the same 12 pages cost 18.56s grouped
        # against 29.28s one call at a time.
        result = converter.convert(pdf_path, page_range=(first, last))
        for page_no in range(first, last + 1):
            try:
                pages[page_no] = result.document.export_to_markdown(page_no=page_no)
            except Exception as exc:
                # One unreadable page should not cost us the rest of the block.
                pages[page_no] = ""
                print(f"page {page_no} failed: {exc}", file=sys.stderr)
        for table in getattr(result.document, "tables", None) or []:
            try:
                flattened = _table_grid(table)
            except Exception as exc:
                print(f"table skipped: {exc}", file=sys.stderr)
                continue
            if flattened:
                tables.append(flattened)
    return {"pages": pages, "tables": tables, "device": cihaz()}


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
