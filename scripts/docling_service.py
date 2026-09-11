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

from _docling_worker import _table_grid, sayfa_bolgeleri, sayfa_markdown

PORT = int(os.environ.get("DOCLING_PORT", "3941"))
DEVICE = (os.environ.get("DOCLING_DEVICE") or "cpu").strip().lower()
ARTIFACTS = (os.environ.get("DOCLING_ARTIFACTS_PATH") or "").strip()
NUM_THREADS = int(os.environ.get("DOCLING_NUM_THREADS", "4"))
#: One conversion at a time by default. There is one card, and a second layout
#: model on it buys nothing while costing VRAM the capacity planner has already
#: reserved for Ollama. The client keeps its own queue in engines.py; this is the
#: limit that actually holds.
MAX_CONCURRENT = max(1, int(os.environ.get("DOCLING_MAX_CONCURRENT", "1")))
#: Idle seconds before the CUDA caching allocator is asked to hand its unused blocks
#: back to the driver. 0 disables the sweep. See _bosta_serbest_birak() for why a
#: resident converter needs one at all.
IDLE_RELEASE_S = float(os.environ.get("DOCLING_IDLE_RELEASE_S", "90"))
#: How often the watcher looks. Well below IDLE_RELEASE_S so the release lands close
#: to the moment the service actually went idle.
IDLE_POLL_S = float(os.environ.get("DOCLING_IDLE_POLL_S", "15"))

_KAPI = threading.BoundedSemaphore(MAX_CONCURRENT)

_SAYAC = threading.Lock()
#: Set by every finished conversion, cleared by the sweep: the allocator owes us a
#: release. Without it an idle service would call into CUDA forever.
_borc = False
_son_is_bitti = time.monotonic()
_serbest_sayisi = 0
_son_serbest: dict | None = None


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
        "idle_release_s": IDLE_RELEASE_S,
        "releases": _serbest_sayisi,
        "last_release": _son_serbest,
        "reserved_bytes": (
            torch.cuda.memory_reserved() if _DEVICE == AcceleratorDevice.CUDA else 0
        ),
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
        # Marked on the failure path too: a conversion that raised still left blocks
        # in the allocator.
        _isi_isaretle()
        _sil(yol)


def _donustur(yol: str, bloklar: list[tuple[int, int]]) -> dict:
    """The same loop `_docling_worker.run()` runs, against the resident converter."""
    started = time.perf_counter()
    pages: dict[int, str] = {}
    tables: list[dict] = []
    regions: list[dict] = []
    for first, last in bloklar:
        result = CONVERTER.convert(yol, page_range=(first, last))
        for page_no in range(first, last + 1):
            try:
                pages[page_no] = sayfa_markdown(result.document, page_no)
            except Exception:
                # One unreadable page must not cost the rest of the block. The client
                # keeps its fast-path text for whatever does not come back.
                pages[page_no] = ""
            try:
                regions.extend(sayfa_bolgeleri(result.document, page_no))
            except Exception:
                # No regions only means the page's markers stay unnumbered.
                pass
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
        "regions": regions,
        "device": _cihaz_adi(),
        "build": BUILD,
        "duration_ms": (time.perf_counter() - started) * 1000,
    }


def _isi_isaretle() -> None:
    """Record that a conversion just ended, so the watcher knows what to wait on."""
    global _borc, _son_is_bitti
    with _SAYAC:
        _borc = True
        _son_is_bitti = time.monotonic()


def _bosta_serbest_birak() -> dict | None:
    """Give the allocator's unused blocks back while nothing is converting.

    torch never returns a block it has cached, so a resident converter's VRAM only
    ratchets up. Measured 2026-09-04 on this deployment: a service two days old held
    4818 MiB against a 1838 MiB single-conversion peak, which left Ollama too little
    of the 8 GB card and pushed 35% of its layers onto the CPU.

    Idle is the right hook, and not only because it is free -- there is no queued work
    to slow down. It is also exactly when the card is wanted elsewhere: docling does
    not run during the pipeline's NORMALIZE stage, which is the LLM's heaviest stretch,
    so the service is naturally idle at the moment Ollama needs the VRAM most.

    Returns None when a conversion holds the gate; the caller keeps the debt and
    retries on the next tick rather than contending for the card.

    This does not return everything: the CUDA context, cuDNN and cuBLAS workspaces
    live outside the caching allocator. The measured floor is ~724 MiB, not zero.
    """
    if _DEVICE != AcceleratorDevice.CUDA:
        return None
    alinan = 0
    try:
        for _ in range(MAX_CONCURRENT):
            if not _KAPI.acquire(blocking=False):
                return None
            alinan += 1
        onceki = torch.cuda.memory_reserved()
        torch.cuda.empty_cache()
        return {
            "reserved_before": onceki,
            "reserved_after": torch.cuda.memory_reserved(),
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
    finally:
        for _ in range(alinan):
            _KAPI.release()


def _gozcu() -> None:
    """Watch for idle and sweep once per idle period."""
    global _borc, _serbest_sayisi, _son_serbest
    while True:
        time.sleep(IDLE_POLL_S)
        with _SAYAC:
            # Clearing the debt before the sweep, not after: a conversion that finishes
            # while empty_cache() runs re-arms it and gets its own sweep next tick.
            hazir = _borc and (time.monotonic() - _son_is_bitti) >= IDLE_RELEASE_S
            if hazir:
                _borc = False
        if not hazir:
            continue
        olcum = _bosta_serbest_birak()
        if olcum is None:
            with _SAYAC:
                _borc = True
            continue
        with _SAYAC:
            _serbest_sayisi += 1
            _son_serbest = olcum


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
    if IDLE_RELEASE_S > 0 and _DEVICE == AcceleratorDevice.CUDA:
        threading.Thread(target=_gozcu, name="idle-release", daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
