#!/usr/bin/env python3
"""Draw each slide of a presentation as a PNG so the polishing agent can see its work.

The presentation polisher copies this file into the agent's working folder as
``render.py``; the agent runs it there::

    python render.py cilali.pptx        # -> render/slide-01.png, render/slide-02.png, ...

Everything, the LibreOffice profile included, stays inside the working folder: the agent
may be sandboxed to it.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf


def find_soffice() -> str | None:
    """The service passes the LibreOffice it validated with; PATH is the fallback."""
    configured = os.environ.get("PRESENTATION_POLISHER_SOFFICE", "")
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("soffice")


def render(deck: Path, out_dir: Path, *, dpi: int, timeout_s: float) -> list[Path]:
    soffice = find_soffice()
    if soffice is None:
        raise RuntimeError("LibreOffice (soffice) was not found")
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("slide-*.png"):
        stale.unlink()
    # LibreOffice's background process can still hold its profile when the launcher has
    # exited (WinError 145, measured 2026-09-16); a leftover folder is not a failed render.
    with tempfile.TemporaryDirectory(
        prefix=".render-", dir=Path.cwd(), ignore_cleanup_errors=True
    ) as tmp:
        tmp_path = Path(tmp)
        completed = subprocess.run(
            [
                soffice,
                # A private profile: a LibreOffice already open on the desktop would
                # otherwise swallow the conversion request and exit without output.
                f"-env:UserInstallation={(tmp_path / 'profile').resolve().as_uri()}",
                "--headless",
                "--convert-to",
                "pdf:impress_pdf_Export",
                str(deck),
                "--outdir",
                str(tmp_path),
            ],
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
        pdf = tmp_path / f"{deck.stem}.pdf"
        if completed.returncode != 0 or not pdf.is_file():
            detail = completed.stderr.decode("utf-8", errors="replace")[-300:]
            raise RuntimeError(f"LibreOffice could not render {deck.name}: {detail}")
        paths: list[Path] = []
        with pymupdf.open(pdf) as document:
            for number, page in enumerate(document, 1):
                path = out_dir / f"slide-{number:02d}.png"
                page.get_pixmap(dpi=dpi).save(path)
                paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render every slide of a deck to PNG.")
    parser.add_argument("deck", type=Path, help="presentation to draw, e.g. cilali.pptx")
    parser.add_argument("--out", type=Path, default=Path("render"), help="output folder")
    parser.add_argument("--dpi", type=int, default=80, help="resolution (80 -> 1067x600)")
    parser.add_argument("--timeout", type=float, default=120.0, help="LibreOffice time limit (s)")
    args = parser.parse_args(argv)
    if not args.deck.is_file():
        print(f"not found: {args.deck}", file=sys.stderr)
        return 2
    try:
        paths = render(args.deck, args.out, dpi=args.dpi, timeout_s=args.timeout)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(exc, file=sys.stderr)
        return 1
    for path in paths:
        print(path.as_posix())
    print(f"{len(paths)} slides rendered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
