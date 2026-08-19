"""
The heavy end of the pipeline: engines that re-extract the pages the gate flagged.

Everything here is optional. Docling installs several gigabytes of torch, so a
deployment that does not want it should still parse PDFs -- just without OCR or
table structure. What must never happen is that absence passing unnoticed: a
scanned PDF yields no text at all, and acquisition drops any document under 400
characters, so "no heavy engine" and "clean document" would otherwise look
identical downstream. Every result carries the profile it was produced under.

Two ways to reach Docling:

  in-process   `import docling` works here. Simplest, but a timeout cannot stop
               a conversion already running.
  bridged      it does not, and SMART_ROUTER_DOCLING_PYTHON names an interpreter
               where it does. Costs process startup per document, and buys a
               timeout that actually kills the work.

DETERMINISM. Selection has to depend on the input alone -- content_hash is derived
from the parsed text and drives dedup, snapshot keys and passage offsets. So the
timeout here is a fixed per-document constant, never a function of system load,
and nothing in this module consults a queue depth or a budget. A timeout still
makes output vary between runs on a loaded machine; that is degradation we can
observe, not determinism, and it is named as such (`degraded`, and a profile
suffix) rather than papered over.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .pages import ardisik_bloklar, docling_page_range, mineru_args

#: Bumped when engine behaviour changes in a way that alters output.
ENGINE_VERSION = "engines_v1_2026-08-18"

#: Fixed per document. Deliberately not derived from load, queue depth or budget.
VARSAYILAN_ZAMAN_ASIMI_SN = 900.0

#: Names an interpreter that has Docling, for when this one does not.
KOPRU_ENV = "SMART_ROUTER_DOCLING_PYTHON"

#: How many heavy extractions may run at once. Each one is a layout model and,
#: bridged, a whole interpreter; letting acquisition start one per document would
#: exhaust memory long before it saturated the CPU. A threading primitive rather
#: than an asyncio one because parse() is synchronous and is called from a worker
#: thread -- see the to_thread call in acquisition.py.
ESZAMANLI_AGIR = max(1, int(os.environ.get("SMART_ROUTER_MAX_CONCURRENT_HEAVY", "1")))

_AGIR_KAPI = threading.BoundedSemaphore(ESZAMANLI_AGIR)

#: How long a document may wait for a slot before giving up. Waiting forever turns
#: a busy queue into a hang; refusing immediately wastes work that would have got a
#: slot shortly. Fixed, not derived from load -- see the determinism note above.
KUYRUK_BEKLEME_SN = 300.0

_SONUC_ISARETI = "__SMART_ROUTER_RESULT__"


@dataclass
class EngineResult:
    """
    What one engine returned for the pages it was asked about.

    `pages` is keyed by 1-based page number, matching the rest of the pipeline.
    A page missing from it was requested but not produced -- the caller keeps its
    fast-path text and records why.
    """

    engine: str
    pages: Dict[int, str] = field(default_factory=dict)
    #: Tables recovered as a grid, not as prose: {"page", "headers", "rows"}.
    tables: List[dict] = field(default_factory=list)
    ok: bool = True
    error: Optional[str] = None
    degraded: bool = False
    duration_ms: float = 0.0
    mode: str = ""
    #: Which accelerator produced this. Measured on an RTX 4060 box: the same PDF
    #: and the same Docling build give DIFFERENT text on CPU and CUDA -- 4 of 9
    #: corpus documents, one losing a whole markdown table. content_hash is the
    #: sha256 of that text, so the device belongs in provenance and two workers on
    #: different accelerators are not interchangeable.
    device: str = ""

    @property
    def profile_suffix(self) -> str:
        """Distinguishes a degraded run from a clean one in provenance."""
        if self.ok and not self.degraded:
            return ""
        return "_degraded" if self.pages else "_no_heavy"


class DoclingEngine:
    """
    Docling over a page list, in-process or bridged to another interpreter.

    Measured against the alternatives on the scanned document (6 pages, ~26,338
    characters expected): Docling recovers 24,963, MinerU 24,554, and every
    text-layer extractor essentially nothing -- pypdf 70, pdf-inspector 0. On the
    200-document benchmark Docling scores 0.894 overall and 0.934 on tables, the
    best of the six libraries measured.
    """

    name = "docling"

    def __init__(
        self,
        *,
        python_path: Optional[str] = None,
        timeout_s: float = VARSAYILAN_ZAMAN_ASIMI_SN,
    ) -> None:
        self.timeout_s = timeout_s
        self.python_path = python_path or os.environ.get(KOPRU_ENV) or ""

    def available(self) -> Tuple[bool, str]:
        if _docling_importable():
            return True, "docling (in-process)"
        if self.python_path and os.path.exists(self.python_path):
            return True, f"docling (bridged via {self.python_path})"
        if self.python_path:
            return False, f"{KOPRU_ENV} points at a missing interpreter: {self.python_path}"
        return False, f"docling not importable and {KOPRU_ENV} is unset"

    def extract(self, pdf_path: str, pages: Sequence[int]) -> EngineResult:
        """Re-extract `pages` (1-based). Consecutive pages are sent as one call."""
        started = time.perf_counter()
        wanted = sorted({int(p) for p in pages})
        if not wanted:
            return EngineResult(engine=self.name, ok=True, mode="noop")

        usable, detail = self.available()
        if not usable:
            return EngineResult(
                engine=self.name, ok=False, degraded=True, error=detail, mode="unavailable",
                duration_ms=(time.perf_counter() - started) * 1000,
            )

        # Backpressure: hold here until a slot frees up rather than starting an
        # unbounded number of models. Callers arrive on worker threads, so blocking
        # is the intended behaviour -- the event loop is not on this stack.
        if not _AGIR_KAPI.acquire(timeout=KUYRUK_BEKLEME_SN):
            return EngineResult(
                engine=self.name, ok=False, degraded=True, mode="queue-timeout",
                error=f"no engine slot within {KUYRUK_BEKLEME_SN:.0f}s "
                      f"({ESZAMANLI_AGIR} concurrent)",
                duration_ms=(time.perf_counter() - started) * 1000,
            )

        blocks = [docling_page_range(b) for b in ardisik_bloklar(wanted)]
        in_process = _docling_importable()
        runner = self._in_process if in_process else self._bridged
        mode = "in-process" if in_process else "bridged"
        try:
            produced, tables, error, device = runner(pdf_path, blocks)
        except Exception as exc:
            produced, tables, error, device = {}, [], f"{type(exc).__name__}: {exc}", ""
        finally:
            _AGIR_KAPI.release()

        missing = [p for p in wanted if p not in produced]
        return EngineResult(
            engine=self.name,
            pages=produced,
            tables=tables,
            ok=error is None and not missing,
            error=error or (f"{len(missing)} pages not produced" if missing else None),
            degraded=bool(error) or bool(missing),
            duration_ms=(time.perf_counter() - started) * 1000,
            mode=mode,
            device=device,
        )

    def _in_process(
        self, pdf_path: str, blocks: List[Tuple[int, int]]
    ) -> Tuple[Dict[int, str], List[dict], Optional[str], str]:
        os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
        from docling.document_converter import DocumentConverter

        from ._docling_worker import _table_grid, cihaz

        converter = DocumentConverter()
        pages: Dict[int, str] = {}
        tables: List[dict] = []
        for first, last in blocks:
            result = converter.convert(pdf_path, page_range=(first, last))
            for page_no in range(first, last + 1):
                try:
                    pages[page_no] = result.document.export_to_markdown(page_no=page_no)
                except Exception:
                    pass
            for table in getattr(result.document, "tables", None) or []:
                try:
                    flattened = _table_grid(table)
                except Exception:
                    continue
                if flattened:
                    tables.append(flattened)
        return pages, tables, None, cihaz()

    def _bridged(
        self, pdf_path: str, blocks: List[Tuple[int, int]]
    ) -> Tuple[Dict[int, str], List[dict], Optional[str], str]:
        # Invoked by file path, not `-m`: importing it as part of the package
        # would pull in registry -> pdf -> pypdf, and the interpreter that has
        # Docling is not required to have the rest of the platform installed.
        worker = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "_docling_worker.py")
        command = [
            self.python_path, worker,
            pdf_path, json.dumps([[a, b] for a, b in blocks]),
        ]
        environment = dict(os.environ)
        environment["TORCHDYNAMO_DISABLE"] = "1"
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self.timeout_s, env=environment,
            )
        except subprocess.TimeoutExpired:
            # The process is killed by the time this raises -- that is the whole
            # reason the bridged mode exists.
            return {}, [], f"timeout after {self.timeout_s:.0f}s", ""

        payload = _son_isaretli_satir(completed.stdout)
        if payload is None:
            tail = (completed.stderr or completed.stdout or "").strip()[-400:]
            return {}, [], f"worker produced no result (exit {completed.returncode}): {tail}", ""
        if "error" in payload:
            return {}, [], str(payload["error"]), ""
        return ({int(k): v for k, v in (payload.get("pages") or {}).items()},
                list(payload.get("tables") or []), None,
                str(payload.get("device") or ""))


class MinerUEngine:
    """
    MinerU as an OCR alternative, kept because Docling garbled a sentence once.

    On the scanned document Docling recovered more characters (24,963 against
    24,554) but turned "unidirectionality constraint by using a masked language
    model" into "unidi-eat i, a inn otlinnolns guage model", which MinerU did not.
    That is a single observation on a single document, so this stays a fallback
    rather than the default.

    NOT EXERCISED YET. The -s/-e flags are confirmed to exist and pages.py
    produces them on the right base, but no run has gone through this path.
    """

    name = "mineru"

    def __init__(self, *, timeout_s: float = VARSAYILAN_ZAMAN_ASIMI_SN) -> None:
        self.timeout_s = timeout_s

    def available(self) -> Tuple[bool, str]:
        return False, "mineru CLI wiring not exercised yet; see class docstring"

    def cli_arguments(self, pages: Sequence[int]) -> List[List[str]]:
        """The -s/-e arguments this engine would be called with, one per block."""
        return [mineru_args(b) for b in ardisik_bloklar(sorted({int(p) for p in pages}))]

    def extract(self, pdf_path: str, pages: Sequence[int]) -> EngineResult:
        usable, detail = self.available()
        return EngineResult(
            engine=self.name, ok=False, degraded=True, error=detail, mode="unavailable"
        )


def _docling_importable() -> bool:
    import importlib.util

    return importlib.util.find_spec("docling") is not None


def _son_isaretli_satir(stdout: str) -> Optional[dict]:
    """Docling prints its own progress; ours is the line carrying the marker."""
    for line in reversed((stdout or "").splitlines()):
        if line.startswith(_SONUC_ISARETI):
            try:
                return json.loads(line[len(_SONUC_ISARETI):])
            except json.JSONDecodeError:
                return None
    return None
