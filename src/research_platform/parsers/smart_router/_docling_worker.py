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


def run(pdf_path: str, blocks: list[list[int]]) -> dict:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    pages: dict[int, str] = {}
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
    return {"pages": pages}


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
