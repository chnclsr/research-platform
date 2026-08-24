"""
Docling behind an HTTP contract, so the worker does not have to carry it.

WHY A SERVICE AND NOT AN IMPORT. engines.py could reach Docling two ways before
this: import it in the worker process, or start a local interpreter that has it.
Neither crosses a container boundary, and the worker image deliberately does not
carry torch -- api, worker, mcp-gateway and telegram-bot all share it. A service
also keeps the models resident: measured 2026-08-21 on the 12-document corpus,
per-document process start plus model load was ~24 s of a 671 s total, about 43%
of the work spent getting ready to work.

WHY THE DEVICE IS ASSERTED, NOT DETECTED. CPU and CUDA do not produce the same
text. Measured on the 261-page corpus: 7 pages differ, one loses a whole markdown
table (research/pdf-parser/results/gpu/README.md). content_hash is the sha256 of
that text, so a silent fall back to CPU would rewrite the identity of every
document parsed while the GPU happened to be missing. DOCLING_DEVICE says what to
use; if it cannot be had, this process exits instead of degrading.

The response is byte-for-byte the shape `_docling_worker.run()` already returns,
so the HTTP and bridged paths parse identically on the client side.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import tempfile
import threading
import time

import torch
import uvicorn
from fastapi import FastAPI, File, Form, UploadFile

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorDevice, AcceleratorOptions, PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

from _docling_worker import _table_grid

PORT = int(os.environ.get("DOCLING_PORT", "3941"))
DEVICE = (os.environ.get("DOCLING_DEVICE") or "cpu").strip().lower()
ARTIFACTS = (os.environ.get("DOCLING_ARTIFACTS_PATH") or "").strip()
NUM_THREADS = int(os.environ.get("DOCLING_NUM_THREADS", "4"))
#: One conversion at a time by default. There is one card, and a second layout
#: model on it buys nothing while costing VRAM the capacity planner has already
#: reserved for Ollama. The client keeps its own queue in engines.py; this is the
#: limit that actually holds.
MAX_CONCURRENT = max(1, int(os.environ.get("DOCLING_MAX_CONCURRENT", "1")))

_KAPI = threading.BoundedSemaphore(MAX_CONCURRENT)


def _surum(paket: str) -> str:
    """Installed version, for /health and for the build string in provenance.

    Read from installation metadata rather than a `__version__` attribute: docling
    does not export one, and the pin in docker/docling-requirements.txt does not by
    itself prove what ended up in the image.
    """
    try:
        return importlib.metadata.version(paket)
    except Exception:
        return "bilinmiyor"


def _cihazi_coz() -> AcceleratorDevice:
    """Resolve DOCLING_DEVICE, or refuse to start.

    A wrong device is not a degraded run, it is a different document -- see the
    module docstring. So this raises rather than picking something that works.
    """
    if DEVICE in ("cuda", "gpu"):
        if not torch.cuda.is_available():
            raise SystemExit(
                "DOCLING_DEVICE=cuda but torch reports no CUDA device. Refusing to "
                "start: CPU output is not interchangeable with GPU output, so falling "
                "back would silently change content_hash. Give the container a GPU "
                "(docker-compose.gpu.yml) or set DOCLING_DEVICE=cpu deliberately."
            )
        return AcceleratorDevice.CUDA
    if DEVICE == "cpu":
        return AcceleratorDevice.CPU
    raise SystemExit(f"DOCLING_DEVICE must be cpu or cuda, got {DEVICE!r}")


_DEVICE = _cihazi_coz()


def _cevirici() -> DocumentConverter:
    options = PdfPipelineOptions()
    options.accelerator_options = AcceleratorOptions(
        device=_DEVICE, num_threads=NUM_THREADS
    )
    if ARTIFACTS:
        # Baked into the image at build time. Naming it keeps a container start from
        # depending on HuggingFace, and keeps one image tag tied to one set of weights.
        options.artifacts_path = ARTIFACTS
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


CONVERTER = _cevirici()

BUILD = (
    f"docling {_surum('docling')}, torch {torch.__version__}, "
    f"{torch.cuda.get_device_name(0) if _DEVICE == AcceleratorDevice.CUDA else 'cpu'}"
)

app = FastAPI()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "device": str(_DEVICE.value if hasattr(_DEVICE, "value") else _DEVICE),
        "build": BUILD,
        "docling": _surum("docling"),
        "torch": torch.__version__,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
        "models": ARTIFACTS or "hf-cache",
        "max_concurrent": MAX_CONCURRENT,
    }


@app.post("/extract")
def extract(file: UploadFile = File(...), blocks: str = Form(...)) -> dict:
    """
    Re-extract page blocks from one PDF.

    Deliberately a sync endpoint: uvicorn runs it on a worker thread, so blocking on
    the semaphore holds that thread rather than the event loop, and /health keeps
    answering while a conversion is in flight.
    """
    try:
        istenen = [(int(a), int(b)) for a, b in json.loads(blocks)]
    except Exception as exc:
        return {"error": f"blocks is not [[first,last],...]: {type(exc).__name__}: {exc}"}
    if not istenen:
        return {"pages": {}, "tables": [], "device": _cihaz_adi(), "build": BUILD}

    yol = _diske_yaz(file)
    if yol is None:
        return {"error": "could not write the upload to a temp file"}
    try:
        with _KAPI:
            return _donustur(yol, istenen)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        _sil(yol)


def _donustur(yol: str, bloklar: list[tuple[int, int]]) -> dict:
    """The same loop `_docling_worker.run()` runs, against the resident converter."""
    started = time.perf_counter()
    pages: dict[int, str] = {}
    tables: list[dict] = []
    for first, last in bloklar:
        result = CONVERTER.convert(yol, page_range=(first, last))
        for page_no in range(first, last + 1):
            try:
                pages[page_no] = result.document.export_to_markdown(page_no=page_no)
            except Exception:
                # One unreadable page must not cost the rest of the block. The client
                # keeps its fast-path text for whatever does not come back.
                pages[page_no] = ""
        for table in getattr(result.document, "tables", None) or []:
            try:
                flattened = _table_grid(table)
            except Exception:
                continue
            if flattened:
                tables.append(flattened)
    return {
        "pages": pages,
        "tables": tables,
        "device": _cihaz_adi(),
        "build": BUILD,
        "duration_ms": (time.perf_counter() - started) * 1000,
    }


def _cihaz_adi() -> str:
    return str(getattr(_DEVICE, "value", _DEVICE))


def _diske_yaz(file: UploadFile) -> str | None:
    """Docling reads a path, not a buffer."""
    try:
        handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    except OSError:
        return None
    try:
        while chunk := file.file.read(1024 * 1024):
            handle.write(chunk)
    except OSError:
        handle.close()
        _sil(handle.name)
        return None
    finally:
        if not handle.closed:
            handle.close()
    return handle.name


def _sil(yol: str) -> None:
    try:
        os.unlink(yol)
    except OSError:
        pass


def main() -> None:
    # Load the models now rather than on the first request, so a client's timeout
    # budget is spent on its own document and not on our startup.
    CONVERTER.initialize_pipeline(InputFormat.PDF)
    uvicorn.run(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
