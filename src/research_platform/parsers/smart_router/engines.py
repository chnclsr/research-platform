"""
The heavy end of the pipeline: engines that re-extract the pages the gate flagged.

Everything here is optional. Docling installs several gigabytes of torch, so a
deployment that does not want it should still parse PDFs -- just without OCR or
table structure. What must never happen is that absence passing unnoticed: a
scanned PDF yields no text at all, and acquisition drops any document under 400
characters, so "no heavy engine" and "clean document" would otherwise look
identical downstream. Every result carries the profile it was produced under.

Three ways to reach Docling, tried in this order:

  service      SMART_ROUTER_DOCLING_URL names a docling service (see
               scripts/docling_service.py). The models stay resident there, so this
               is the only mode that does not pay model load per document --
               measured 2026-08-21, that was ~24 s of every document's cost, about
               43% of a 671 s corpus run. It is also the only mode that can be given
               a GPU the worker container does not have.
  bridged      SMART_ROUTER_DOCLING_PYTHON names a local interpreter that has
               Docling. Costs process startup per document, and buys a timeout that
               actually kills the work. Cannot cross a container boundary.
  in-process   `import docling` works right here. Simplest and OFF BY DEFAULT: a
               conversion already running in this process cannot be stopped, and
               parse() is called from a worker thread that acquisition cannot cancel
               either, so an overrun holds the single heavy slot until it finishes on
               its own. SMART_ROUTER_ALLOW_IN_PROCESS=1 accepts that trade.

  CHANGED 2026-08-21: this module used to describe two modes and to prefer
  in-process over bridged. Both changed -- the service mode was added, and
  in-process went from "first choice" to "explicit opt-in" -- because the no-timeout
  hole above is reachable the moment anyone installs docling into the worker image.

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
ENGINE_VERSION = "engines_v2_2026-08-21"

#: Fixed per document. Deliberately not derived from load, queue depth or budget --
#: but it IS derived from the deployment, because a CPU deployment is several times
#: slower than a GPU one and a single number cannot serve both. Same reasoning as the
#: device itself: a declared parameter, constant for the life of the process.
VARSAYILAN_ZAMAN_ASIMI_SN = float(os.environ.get("SMART_ROUTER_HEAVY_TIMEOUT_S", "900"))

#: Names an interpreter that has Docling, for when this one does not.
KOPRU_ENV = "SMART_ROUTER_DOCLING_PYTHON"

#: Names a docling service. Preferred over both local modes when set.
URL_ENV = "SMART_ROUTER_DOCLING_URL"

#: Accepts the in-process path despite its missing timeout. See the module docstring.
IC_SUREC_ENV = "SMART_ROUTER_ALLOW_IN_PROCESS"

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
#:
#: Deployment-dependent for the same reason the timeout is. Measured 2026-08-21 on 12
#: real corpus documents: 138 routed pages cost 671 s bridged on CPU, of which ~288 s
#: was per-document startup a resident service does not pay. At 300 s the tail of that
#: queue cannot get a slot and comes back `queue-timeout` degraded -- which for a
#: scanned PDF means the document is dropped by acquisition's 400-character check, not
#: merely weakened. GPU deployments keep 300; CPU ones raise it (docker-compose.yml).
KUYRUK_BEKLEME_SN = float(os.environ.get("SMART_ROUTER_QUEUE_WAIT_S", "300"))

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
    #: Which docling/torch/accelerator build produced this, as the engine reports it.
    #: The device alone does not pin the output: a docling upgrade changes the text on
    #: the same card. Recorded next to the device for the same reason -- an audit has to
    #: be able to explain a content_hash that moved without the document moving.
    build: str = ""

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

    def _mode(self) -> Optional[str]:
        """Which local path this engine would take, or None if it cannot run.

        Bridged is preferred over in-process even when both are possible: only the
        bridged path can be timed out. Before 2026-08-21 in-process won this
        comparison and `available()` and `extract()` resolved it separately, so the
        two could disagree about which one was in play.
        """
        if self.python_path and os.path.exists(self.python_path):
            return "bridged"
        if not self.python_path and _docling_importable() and _in_process_allowed():
            return "in-process"
        return None

    def available(self) -> Tuple[bool, str]:
        mode = self._mode()
        if mode == "bridged":
            return True, f"docling (bridged via {self.python_path})"
        if mode == "in-process":
            return True, "docling (in-process, NO TIMEOUT)"
        if self.python_path:
            return False, f"{KOPRU_ENV} points at a missing interpreter: {self.python_path}"
        if _docling_importable():
            return False, (
                f"docling is importable here but the in-process path is off ({IC_SUREC_ENV} "
                "unset): a conversion running in this process cannot be timed out and would "
                f"hold the only heavy slot. Point {URL_ENV} at the docling service, or name "
                f"an interpreter with {KOPRU_ENV}, or set {IC_SUREC_ENV}=1 to accept it"
            )
        # Only about what THIS engine controls. Naming URL_ENV here read as "the
        # service is unset" even when it was set and merely unreachable -- the
        # service engine reports its own state, one note above this one.
        return False, f"docling not importable here and {KOPRU_ENV} is unset"

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
        mode = self._mode()
        runner = self._in_process if mode == "in-process" else self._bridged
        try:
            produced, tables, error, device, build = runner(pdf_path, blocks)
        except Exception as exc:
            produced, tables, error = {}, [], f"{type(exc).__name__}: {exc}"
            device = build = ""
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
            mode=mode or "",
            device=device,
            build=build,
        )

    def _in_process(
        self, pdf_path: str, blocks: List[Tuple[int, int]]
    ) -> Tuple[Dict[int, str], List[dict], Optional[str], str, str]:
        os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
        from docling.document_converter import DocumentConverter

        from ._docling_worker import _table_grid, cihaz, yapi

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
        return pages, tables, None, cihaz(), yapi()

    def _bridged(
        self, pdf_path: str, blocks: List[Tuple[int, int]]
    ) -> Tuple[Dict[int, str], List[dict], Optional[str], str, str]:
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
            return {}, [], f"timeout after {self.timeout_s:.0f}s", "", ""

        payload = _son_isaretli_satir(completed.stdout)
        if payload is None:
            tail = (completed.stderr or completed.stdout or "").strip()[-400:]
            return ({}, [],
                    f"worker produced no result (exit {completed.returncode}): {tail}", "", "")
        if "error" in payload:
            return {}, [], str(payload["error"]), "", ""
        return ({int(k): v for k, v in (payload.get("pages") or {}).items()},
                list(payload.get("tables") or []), None,
                str(payload.get("device") or ""), str(payload.get("build") or ""))


#: How long a service /health answer is reused. Probing per document would spend a
#: round trip on every PDF; a stale answer costs at most one extraction, and that
#: already degrades into "kept the fast-path text" rather than into a lost page.
SAGLIK_TAZE_SN = 30.0

#: url -> (checked_at, ok, detail, device, build)
_SAGLIK: Dict[str, Tuple[float, bool, str, str, str]] = {}
_SAGLIK_KILIT = threading.Lock()


class HttpDoclingEngine:
    """
    Docling as a service, over the same JSON payload the bridged worker prints.

    This is the only mode that can put the heavy path on a GPU the worker container
    does not have, and the only one where the models stay resident between documents.
    Measured 2026-08-21 on 12 corpus documents: per-document process start plus model
    load was ~24 s of a 671 s bridged CPU run.

    Deliberately NOT named "docling": provenance keys engine counts and devices by this
    name, and `_run_heavy_pages` keys its `requested` map by it too, so a service result
    and a local result have to stay distinguishable when both run for one document.
    """

    name = "docling-service"

    def __init__(
        self,
        *,
        url: Optional[str] = None,
        timeout_s: float = VARSAYILAN_ZAMAN_ASIMI_SN,
    ) -> None:
        self.url = (url or os.environ.get(URL_ENV) or _ayardan_url()).strip().rstrip("/")
        self.timeout_s = timeout_s

    def available(self) -> Tuple[bool, str]:
        if not self.url:
            return False, f"{URL_ENV} is unset"
        ok, detail, _, _ = self._saglik()
        return ok, detail

    def _saglik(self) -> Tuple[bool, str, str, str]:
        """(ok, detail, device, build), cached for SAGLIK_TAZE_SN."""
        simdi = time.monotonic()
        with _SAGLIK_KILIT:
            onbellek = _SAGLIK.get(self.url)
            if onbellek and simdi - onbellek[0] < SAGLIK_TAZE_SN:
                return onbellek[1], onbellek[2], onbellek[3], onbellek[4]

        import httpx  # noqa: PLC0415 -- see the guarded-import note in ayarlar.py

        try:
            response = httpx.get(f"{self.url}/health", timeout=5.0)
            response.raise_for_status()
            payload = response.json()
            device = str(payload.get("device") or "")
            build = str(payload.get("build") or "")
            sonuc = (True, f"docling service at {self.url} ({build or device or 'no build'})",
                     device, build)
        except Exception as exc:
            sonuc = (False, f"docling service at {self.url} unreachable "
                            f"({type(exc).__name__}: {exc})", "", "")

        with _SAGLIK_KILIT:
            _SAGLIK[self.url] = (simdi, *sonuc)
        return sonuc

    def extract(self, pdf_path: str, pages: Sequence[int]) -> EngineResult:
        """Re-extract `pages` (1-based) on the service. Consecutive pages go as one block."""
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

        # Client-side backpressure. The service has its own limit -- one conversion per
        # card -- and that is the one that protects VRAM; this one keeps acquisition
        # from holding an unbounded number of uploads open against it.
        if not _AGIR_KAPI.acquire(timeout=KUYRUK_BEKLEME_SN):
            return EngineResult(
                engine=self.name, ok=False, degraded=True, mode="queue-timeout",
                error=f"no engine slot within {KUYRUK_BEKLEME_SN:.0f}s "
                      f"({ESZAMANLI_AGIR} concurrent)",
                duration_ms=(time.perf_counter() - started) * 1000,
            )

        blocks = [docling_page_range(b) for b in ardisik_bloklar(wanted)]
        try:
            produced, tables, error, device, build = self._istek(pdf_path, blocks)
        except Exception as exc:
            produced, tables, error = {}, [], f"{type(exc).__name__}: {exc}"
            device = build = ""
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
            mode="http",
            device=device,
            build=build,
        )

    def _istek(
        self, pdf_path: str, blocks: List[Tuple[int, int]]
    ) -> Tuple[Dict[int, str], List[dict], Optional[str], str, str]:
        # The bytes go over the wire rather than through a shared volume: the worker
        # already spills the PDF to its own temp file (smart_pdf._spill_to_disk) and a
        # mount would tie the two containers' filesystems together for nothing.
        import httpx  # noqa: PLC0415

        try:
            with open(pdf_path, "rb") as handle:
                response = httpx.post(
                    f"{self.url}/extract",
                    files={"file": ("document.pdf", handle, "application/pdf")},
                    data={"blocks": json.dumps([[a, b] for a, b in blocks])},
                    timeout=self.timeout_s,
                )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return {}, [], f"{type(exc).__name__}: {exc}", "", ""

        if not isinstance(payload, dict):
            return {}, [], f"service returned {type(payload).__name__}, expected an object", "", ""
        if "error" in payload:
            return {}, [], str(payload["error"]), "", ""
        return ({int(k): v for k, v in (payload.get("pages") or {}).items()},
                list(payload.get("tables") or []), None,
                str(payload.get("device") or ""), str(payload.get("build") or ""))


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


def _ayardan_url() -> str:
    """`smart_router_docling_url` from Settings, so a `.env` entry is honoured too.

    Guarded for the same reason `ayarlar._ayar_dosyasindan_yol()` is: the measurement
    scripts import this package directly, in interpreters that have PyMuPDF but not
    necessarily pydantic-settings. A missing platform config is not an error here, it
    just means the environment variable decides.
    """
    try:
        from ...config import get_settings  # noqa: PLC0415

        return (get_settings().smart_router_docling_url or "").strip()
    except Exception:
        return ""


def _in_process_allowed() -> bool:
    """Whether the caller has accepted the in-process path's missing timeout."""
    return (os.environ.get(IC_SUREC_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


def _son_isaretli_satir(stdout: str) -> Optional[dict]:
    """Docling prints its own progress; ours is the line carrying the marker."""
    for line in reversed((stdout or "").splitlines()):
        if line.startswith(_SONUC_ISARETI):
            try:
                return json.loads(line[len(_SONUC_ISARETI):])
            except json.JSONDecodeError:
                return None
    return None
