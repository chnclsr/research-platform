"""
Page-routed PDF parsing.

Where PdfParser sends every page through one extractor, this parser inspects each
page first and only spends the expensive engine on pages that need it: a scanned
page, a page holding a table, or a page whose extracted text fails a quality
check. Measured on a 9-document / 261-page corpus, 44% of pages stay on the cheap
path, and the routing decision itself costs 0.65-14.84 ms/page -- against seconds
per page for the engine it decides whether to run.

The `# Page N` headings are emitted here for the same reason PdfParser emits them:
chunk_document() derives `page_number` from them (see passages.py). Because pages
can come from different engines, the headings are applied once after the pages are
merged rather than by each engine.
"""

from __future__ import annotations

import logging
import os
import tempfile

from .base import DocumentParser, ParsedDocument, ParsedTable

logger = logging.getLogger(__name__)

try:
    from .smart_router import PDFCritic, ROUTER_VERSION, SmartRouterHatti
    from .smart_router.ayarlar import AYAR
    from .smart_router.engines import (
        ENGINE_VERSION, DoclingEngine, EngineResult, MinerUEngine,
    )
    from .smart_router.gate import ESIK_VERSION
    from .smart_router.merge import MergedDocument, birlestir, sayfa_basliklariyla

    _ROUTER_IMPORT_ERROR: str = ""
except Exception as exc:  # pragma: no cover - exercised only when deps are absent
    SmartRouterHatti = None  # type: ignore[assignment]
    AYAR = None  # type: ignore[assignment]
    ROUTER_VERSION = ESIK_VERSION = ""
    _ROUTER_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


class SmartPdfParser(DocumentParser):
    """
    PDF parser that routes individual pages to the engine each one needs.

    Registered alongside PdfParser rather than replacing it: `priority` decides
    which one wins, so dropping the priority (or returning False from available())
    reverts the pipeline to the plain extractor without touching the registry.
    """

    id = "smart_pdf"
    document_types = ("pdf",)
    capabilities = ("text", "pages")
    # ParserRegistry.select() sorts by (-priority, id), so a tie with PdfParser
    # would hand the document to "pdf" on the alphabetical tiebreak.
    priority = 10

    # CODEX-2026-08-18: Registry selection does not consult health(). If the
    # router package itself failed to import, decline the document so PdfParser
    # can handle it instead of selecting this parser and returning an empty body.
    def can_parse(self, document_type: str, content_type: str, content: bytes) -> bool:
        return SmartRouterHatti is not None and super().can_parse(
            document_type, content_type, content
        )

    def available(self) -> tuple[bool, str]:
        """
        Report the heavy path too, not just whether the router imports.

        Reporting only the router made health() useless for the case that matters
        most: with no OCR engine a scanned PDF yields 68 characters and acquisition
        discards it on the 400-character check, while health still said
        "configured". Not a regression -- the plain pdf parser produces the same 68
        characters on that document -- but an operator had no way to see it coming.

        Still True when the engine is missing: the fast path handles text PDFs on
        its own, and returning False would disable page routing altogether rather
        than degrade it. The detail string is where the difference shows.

        A threshold profile that failed to load degrades the same way -- routing
        still works on the embedded defaults -- so it is reported here rather than
        raised. Otherwise a typo in the YAML would silently change which pages get
        the heavy engine and nothing would say so.
        """
        if SmartRouterHatti is None:
            return False, f"smart_router unavailable ({_ROUTER_IMPORT_ERROR})"
        profil = f"profile {AYAR.esik_version}"
        if AYAR.uyarilar:
            profil += f" (DEFAULTS: {'; '.join(AYAR.uyarilar)})"
        engine_ready, engine_detail = DoclingEngine().available()
        if engine_ready:
            return True, f"smart_router, {profil}, heavy path via {engine_detail}"
        return True, (
            f"smart_router, {profil}, TEXT ONLY -- no heavy engine ({engine_detail}); "
            "scanned PDFs will not survive acquisition"
        )

    def parse(self, content: bytes, *, url: str, content_type: str = "") -> ParsedDocument:
        if SmartRouterHatti is None:
            return self._empty("smart_router unavailable", _ROUTER_IMPORT_ERROR)

        path = self._spill_to_disk(content)
        if path is None:
            return self._empty("could not write the document to a temp file", "")
        try:
            decision = SmartRouterHatti().calistir(path, metin_dahil=True)
            merged = self._run_heavy_pages(path, decision)
        except Exception as exc:
            # A truncated or mislabelled download must not abort acquisition -- the
            # caller rejects the document on the resulting empty text instead. But
            # the same catch hides genuine bugs, and an empty result is
            # indistinguishable from a corrupt file, so say what happened in both
            # the log and the provenance rather than returning silence.
            logger.exception("smart_pdf failed to parse %s", url)
            return self._empty("parse raised", f"{type(exc).__name__}: {exc}")
        finally:
            self._discard(path)

        return ParsedDocument(
            text=sayfa_basliklariyla(merged),
            document_type="pdf",
            parser_id=self.id,
            page_count=merged.page_count,
            tables=self._tables(merged),
            parse_provenance=self._provenance(decision, merged),
        )

    def _tables(self, merged: MergedDocument) -> list[ParsedTable]:
        """
        Keep the recovered tables as grids alongside the prose.

        The markdown rendering already carries them inline, so passages stay
        self-contained; this is for consumers that need to know which number sits
        in which column, which is exactly what flattening a table into prose
        destroys. `section_path` matches the page heading so a table can be traced
        back to where it came from.
        """
        return [
            ParsedTable(
                section_path=f"Page {table['page']}" if table.get("page") else "",
                headers=[str(h) for h in table.get("headers") or []],
                rows=[[str(cell) for cell in row] for row in table.get("rows") or []],
            )
            for table in merged.tables
        ]

    def _empty(self, reason: str, detail: str) -> ParsedDocument:
        """
        An empty result that still says why it is empty.

        Acquisition turns a short parse into a dropped document, so an empty
        ParsedDocument with no explanation is a source disappearing with no trail.
        """
        return ParsedDocument(
            document_type="pdf",
            parser_id=self.id,
            parse_provenance={
                "parser_profile": "smart_pdf_failed",
                "router_version": ROUTER_VERSION,
                "degraded": True,
                "notes": [reason] + ([detail] if detail else []),
            },
        )

    def _provenance(self, decision: dict, merged: MergedDocument) -> dict:
        """
        Record how this document was parsed, page by page.

        Without it a mixed document is indistinguishable from a fast-path one, and
        a document parsed with no heavy engine available looks exactly like a clean
        one -- which matters, because acquisition drops anything under 400
        characters and a scanned PDF with no OCR available produces almost nothing.

        The version strings are here so a later calibration change can tell which
        documents predate it. None of this feeds content_hash: the hash comes from
        the parsed text alone, so a profile change does not fabricate a new version.
        """
        profile = decision.get("parser_profile") or ""
        if merged.degraded:
            profile = f"{profile}_degraded"
        return {
            "parser_profile": profile,
            "router_version": ROUTER_VERSION,
            # From the run, not the module: the threshold profile is a file that a
            # deployment can point elsewhere, so the version that parsed THIS
            # document is the one worth recording. Falls back to the module
            # constant when the router never ran (parse failure path).
            "esik_version": decision.get("esik_version") or ESIK_VERSION,
            "esik_profili": decision.get("esik_profili"),
            "engine_version": ENGINE_VERSION,
            # Which accelerator the heavy engine ran on. Measured on an RTX 4060
            # box: the same PDF and Docling build give different text on CPU and
            # CUDA -- 4 of 9 corpus documents, one losing a whole markdown table.
            # content_hash is the sha256 of that text, so a document parsed on one
            # device is not interchangeable with the same document parsed on
            # another, and an operator has to be able to see which was used.
            "engine_devices": merged.engine_devices,
            "degraded": merged.degraded,
            "notes": merged.notes,
            "engine_counts": merged.engine_counts,
            "fallback_pages": merged.fallback_pages,
            "quarantined_pages": merged.quarantined_pages,
            "pages": [
                {"page": page.page_no, "engine": page.engine,
                 "decision": page.decision, "fell_back": page.fell_back}
                for page in merged.pages
            ],
        }

    def _run_heavy_pages(self, path: str, decision: dict) -> MergedDocument:
        """
        Send the flagged pages to the heavy engine and merge what comes back.

        The engine is optional and may be missing, time out, or return nothing for
        a page. None of those lose the page: it keeps its fast-path text and the
        merge records that it fell back, so a degraded document stays
        distinguishable from a clean one.
        """
        fast_pages = {int(k): v for k, v in (decision.get("sayfa_metni") or {}).items()}
        decisions = {
            int(page["sayfa_no"]): list(page.get("karar_kaynagi") or [])
            for page in decision.get("sayfalar") or []
        }
        heavy = sorted(page for page, reasons in decisions.items() if reasons)
        if not heavy:
            return birlestir(fast_pages, decisions=decisions)

        results = []
        requested: dict[str, list[int]] = {}
        outstanding = list(heavy)
        # Ordered fallback rather than one hard-coded engine: if the first cannot
        # run or misses pages, the next gets what is left. MinerU currently reports
        # itself unavailable, so in practice this is Docling alone -- but the shape
        # is here so wiring MinerU up is a change in one place, not a rewrite.
        for engine in (DoclingEngine(), MinerUEngine()):
            if not outstanding:
                break
            usable, _ = engine.available()
            requested[engine.name] = list(outstanding)
            if not usable:
                # CODEX-2026-08-18: Keep the concrete availability failure in
                # per-document provenance; a generic "heavy miss" is not enough.
                results.append(engine.extract(path, outstanding))
                continue
            try:
                result = engine.extract(path, outstanding)
            except Exception as exc:
                result = EngineResult(
                    engine=engine.name, ok=False, degraded=True,
                    error=f"{type(exc).__name__}: {exc}", mode="raised",
                )
            results.append(result)
            outstanding = [p for p in outstanding if p not in result.pages]

        return birlestir(
            fast_pages, decisions=decisions, results=results, requested=requested,
            score=self._page_scorer(),
        )

    def _page_scorer(self):
        """
        Grade a page on corruption alone -- the only thing comparable across engines.

        The obvious implementation, scoring both versions with the composite quality
        score and keeping the higher, systematically reverses the routing it is
        meant to protect. Measured on turkce_makale page 3: the fast path scored
        92.4 with table_irregularity 0.000 over 3,485 characters, Docling scored
        85.3 with table_irregularity 0.368 over 18,215. The fast path won because it
        had emitted no table at all -- nothing to be irregular about -- while the
        engine that actually read the table was penalised for having produced one.
        That check would have discarded exactly the pages routing exists to rescue.

        So the comparison is narrowed to signals that mean the same thing whichever
        engine produced the text: gibberish and broken encoding.

        WHAT THIS DOES NOT CATCH. The failure that motivated the check -- Docling
        turning "unidirectionality constraint by using a masked language model"
        into "unidi-eat i, a inn otlinnolns guage model" -- is not detected by any
        of the twelve page metrics; measured, all twelve read identically on the
        two strings. They were built for layout and extraction faults, not for OCR
        producing plausible-looking wrong words. And that observation was on a
        scanned page, where the fast path has no text at all, so no comparison
        against it is possible even in principle. Catching that class of error
        needs a lexical check this pipeline does not have yet.

        What the check does buy: a heavy engine that returns encoding-corrupt or
        empty text for a page we already had clean text for no longer overwrites it.

        NOTE. These two coefficients weigh the same two signals the gate's quality
        score already weighs, at different values: the gate charges 10.0 for unicode
        corruption and scales gibberish by 300, this check charges 20.0 and scales
        by 100. Two calibrations of one pair of signals. Both now live in the
        threshold profile so the discrepancy is at least visible in one file; which
        pair is right is a calibration question (plan D12), not a merge question.
        """
        critic = PDFCritic()
        gibberish_kat = AYAR.corruption["gibberish_kat"]
        unicode_ceza = AYAR.corruption["unicode_ceza"]

        def score(text: str):
            metrics = critic.sayfa_metrikleri(text)
            corruption = metrics["gibberish_ratio"] * gibberish_kat
            if metrics["unicode_bozuk"]:
                corruption += unicode_ceza
            return 100.0 - corruption

        return score

    def _spill_to_disk(self, content: bytes) -> str | None:
        """
        The router and every engine below it read a path, not a buffer.

        The handle is closed before the path is handed on: on Windows a second
        process cannot open a file we still hold open, so `delete=True` would make
        the engines fail rather than clean up after us.
        """
        try:
            handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        except OSError:
            return None
        try:
            handle.write(content)
        except OSError:
            handle.close()
            self._discard(handle.name)
            return None
        finally:
            if not handle.closed:
                handle.close()
        return handle.name

    def _discard(self, path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            # Losing a temp file is not worth failing an acquisition over.
            pass
