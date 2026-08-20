"""
Combines fast-path pages with the ones a heavy engine re-extracted.

Pages arrive from different engines, so this is where a document becomes one
document again. Two things have to hold afterwards:

  * Every page the router saw appears exactly once, in order. A page the heavy
    engine was asked for but did not return keeps its fast-path text rather than
    vanishing -- losing a page silently is worse than serving a weaker version of
    it.
  * Each page records which engine produced it. `ParsedDocument.parser_id` is one
    string for the whole document, so per-page origin has nowhere else to go, and
    without it a mixed document is indistinguishable from a fast-path one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .ayarlar import AYAR
from .engines import EngineResult

# Levels 1-5 shift down one; level 6 has nowhere to go and is left alone.
_HEADING = re.compile(r"(?m)^(\s{0,3})(#{1,5})(\s+\S)")


def nest_under_page(markdown: str) -> str:
    """
    Push a page's own headings one level down so `# Page N` stays the only level-1.

    _sections() in passages.py builds a hierarchical section path and drops every
    ancestor at or above the current heading's level, so a level-1 heading inside a
    page evicts `Page N` from the path entirely and every passage after it loses its
    page number -- silently, as page_number=None rather than an error. Demoting the
    page's own headings keeps them nested underneath the page heading instead.
    """
    return _HEADING.sub(r"\1#\2\3", markdown)


@dataclass
class MergedPage:
    page_no: int
    text: str
    engine: str
    #: Why this page was routed where it was, from the page selector.
    decision: List[str] = field(default_factory=list)
    #: The heavy engine was asked for this page and did not deliver it.
    fell_back: bool = False
    #: Corruption scores from the last quarantine check run on this page
    #: (None if no heavy engine was ever compared against it -- see _karar_ver).
    fast_skor: Optional[float] = None
    heavy_skor: Optional[float] = None
    #: Human-readable reason the last quarantine check picked what it picked.
    karar_gerekcesi: Optional[str] = None


@dataclass
class MergedDocument:
    pages: List[MergedPage] = field(default_factory=list)
    #: Engine name -> how many pages it actually produced.
    engine_counts: Dict[str, int] = field(default_factory=dict)
    #: Engine name -> the accelerator it ran on. Measured on an RTX 4060 box: the
    #: same PDF and Docling build give different text on CPU and CUDA (4 of 9
    #: corpus documents, one losing a whole markdown table). content_hash is the
    #: sha256 of that text, so which device produced a page belongs with which
    #: engine produced it.
    engine_devices: Dict[str, str] = field(default_factory=dict)
    #: Pages the heavy path was supposed to handle but did not.
    fallback_pages: List[int] = field(default_factory=list)
    #: Tables the heavy engine recovered as a grid: {"page", "headers", "rows"}.
    tables: List[dict] = field(default_factory=list)
    #: Pages where the heavy engine produced text but scored no better than the
    #: fast path, so the fast text was kept.
    quarantined_pages: List[int] = field(default_factory=list)
    degraded: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)


#: Docling's own marker for a formula region it found but could not decode
#: (do_formula_enrichment=False today, see entegrasyon_plani.md Q1/Q2). Its
#: presence in the heavy text where the fast text has none of it is treated
#: as catastrophic regardless of the corruption-score comparison below --
#: an exact string match, not a heuristic, so it costs nothing to trust.
FORMUL_COZULEMEDI_ISARETI = "<!-- formula-not-decoded -->"


@dataclass
class _Karar:
    """One quarantine decision: whether the heavy page replaces the fast one."""
    kabul: bool
    gerekce: str
    fast_skor: Optional[float] = None
    heavy_skor: Optional[float] = None


def _karar_ver(
    score: Optional[Callable[[str], Optional[float]]], fast: str, heavy: str,
    tolerans: float = 0.0,
) -> _Karar:
    """
    Decide whether the heavy engine's page replaces the fast one it is being
    compared to. `heavy` is assumed non-empty -- birlestir() already discards
    an empty heavy page before this is called.

    Four cases:

      1. Fast is empty, heavy is not flagged catastrophic -> accept, nothing
         to lose (unchanged from the pipeline's original behaviour).
      2. Fast is empty, heavy IS flagged catastrophic -> accept anyway --
         rejecting would just leave the empty fast text, which is no better --
         but say so, so provenance does not read this as a clean win. There is
         no third engine to fall back to today (MinerU is not wired in, see
         engines.py); the gerekce names that rather than pretending otherwise.
      3. Fast has text, heavy is flagged catastrophic -> reject, keep fast.
      4. Fast has text, heavy is not flagged catastrophic -> compare
         corruption scores with a dead band (`tolerans` -- see
         config/smart_router.yaml for the measurement behind 0.1). Unscoreable
         either way (no scorer, a grader that returns None) means we cannot
         tell, and heavy wins by default -- it was requested for a reason.

    "Catastrophic" is deliberately narrow and one-directional: it only fires
    on Docling's unresolved-formula placeholder appearing in heavy but not in
    fast. It is NOT a broad quality check -- see _page_scorer's docstring
    (smart_pdf.py) for the measured example (turkce_makale page 3) of why
    scoring both sides on the same composite metric reverses the routing it
    is meant to protect: an engine that reads a table correctly gets
    penalised for the table looking "irregular" next to no table at all.
    """
    heavy_katastrofik = (
        FORMUL_COZULEMEDI_ISARETI in heavy and FORMUL_COZULEMEDI_ISARETI not in fast
    )

    if not fast.strip():
        if heavy_katastrofik:
            return _Karar(True, "fast_bos_heavy_de_bozuk_alternatif_yok")
        return _Karar(True, "fast_bos_heavy_kullanilabilir")

    if heavy_katastrofik:
        return _Karar(False, "heavy_formul_cozulemedi")

    if score is None:
        return _Karar(True, "skorlanamadi_varsayilan_heavy")
    try:
        fast_skor, heavy_skor = score(fast), score(heavy)
    except Exception:
        return _Karar(True, "skor_hatasi_varsayilan_heavy")
    if fast_skor is None or heavy_skor is None:
        return _Karar(True, "skorlanamadi_varsayilan_heavy", fast_skor, heavy_skor)

    fark = heavy_skor - fast_skor
    if fark >= -tolerans:
        return _Karar(True, f"skor_farki_kabul ({fark:+.3f})", fast_skor, heavy_skor)
    return _Karar(False, f"skor_farki_red ({fark:+.3f})", fast_skor, heavy_skor)


def birlestir(
    fast_pages: Dict[int, str],
    *,
    fast_engine: str = "pdf-inspector",
    results: Sequence[EngineResult] = (),
    decisions: Optional[Dict[int, List[str]]] = None,
    requested: Optional[Dict[str, Sequence[int]]] = None,
    score: Optional[Callable[[str], Optional[float]]] = None,
    tolerans: float = AYAR.karantina_tolerans,
) -> MergedDocument:
    """
    Merge fast-path text with heavy-engine output, page by page.

    `fast_pages` is the full document as the cheap parser saw it, keyed by 1-based
    page number -- it defines which pages exist. `results` are the heavy engines'
    returns; later results win, so pass them in the order they should override.
    `requested` maps engine name to the pages it was asked about, which is how a
    page that was routed to a heavy engine but came back empty is told apart from
    one that was never routed there at all.

    `score` grades one page of text, higher being better. When given, a heavy
    engine's page only replaces the fast one if it does not score worse -- the
    output check the pipeline was missing. Without it every non-empty heavy page
    wins, which is the old behaviour.

    `tolerans` widens that check to `heavy >= fast - tolerans`. Default comes from
    the profile (`config/smart_router.yaml`, 0.1 as of 2026-08-20): measured over
    261 pages, 16 of 37 quarantines at tolerans=0.0 had the two scores within 0.1
    of each other -- the corruption score cannot reliably tell those apart, so
    treating them as ties (accept heavy) rather than losses costs nothing measured
    so far, and the 19 larger drops (including a -22.38 outlier) still quarantine
    at 0.1. See the profile file for the full sweep and entegrasyon_plani.md
    Bölüm 17 madde #1 for the page-by-page review behind this call.
    """
    decisions = decisions or {}
    requested = requested or {}

    winner: Dict[int, tuple[str, str]] = {}
    counts: Dict[str, int] = {}
    table_candidates: List[tuple[str, dict]] = []
    notes: List[str] = []
    degraded = False

    # Every rejected attempt, engine by engine -- may include a page a LATER
    # engine went on to win. Filtered down to the final quarantine list once
    # every result has been processed (CODEX-2026-08-18's note below still
    # applies to the table side of this).
    denenip_reddedilen: List[int] = []
    kararlar: Dict[int, _Karar] = {}
    devices: Dict[str, str] = {}
    for result in results:
        if result.device:
            devices[result.engine] = result.device
        table_candidates.extend((result.engine, table) for table in result.tables)
        if result.degraded or not result.ok:
            degraded = True
            if result.error:
                notes.append(f"{result.engine}: {result.error}")
        for page_no, text in result.pages.items():
            # An engine that returns an empty page has not improved on the fast
            # path, and overwriting with it would lose text we already had.
            if not (text and text.strip()):
                continue
            page_no = int(page_no)
            karar = _karar_ver(score, fast_pages.get(page_no, ""), text, tolerans)
            kararlar[page_no] = karar
            if not karar.kabul:
                # Being expensive does not make output better. Docling was once
                # observed turning "unidirectionality constraint by using a masked
                # language model" into "unidi-eat i, a inn otlinnolns guage model"
                # on a scanned page -- overwriting blindly would have shipped that.
                denenip_reddedilen.append(page_no)
                continue
            winner[page_no] = (text, result.engine)

    # A page only counts as quarantined if NO engine's attempt won it -- an
    # earlier engine's rejection must not outlive a later engine's acceptance.
    quarantined = sorted(set(p for p in denenip_reddedilen if p not in winner))
    if quarantined:
        degraded = True
        notes.append(
            f"{len(quarantined)} pages kept fast-path text: the heavy engine scored "
            f"lower ({quarantined})"
        )

    # Pages where the fast path had nothing to compare against and the heavy
    # result was itself flagged catastrophic (see _karar_ver) -- accepted
    # because there is no third option today (MinerU is not wired in, see
    # engines.py), but flagged so provenance does not read this as a clean win.
    alternatifsiz_kabul = sorted(
        p for p, k in kararlar.items()
        if p in winner and k.gerekce == "fast_bos_heavy_de_bozuk_alternatif_yok"
    )
    if alternatifsiz_kabul:
        degraded = True
        notes.append(
            f"{len(alternatifsiz_kabul)} pages had no usable fast text and a "
            f"flagged-corrupt heavy result was kept anyway, no alternative engine "
            f"available ({alternatifsiz_kabul})"
        )

    asked_about: Dict[int, str] = {}
    for engine, pages in requested.items():
        for page_no in pages:
            asked_about[int(page_no)] = engine

    merged: List[MergedPage] = []
    fallbacks: List[int] = []
    for page_no in sorted(fast_pages):
        if page_no in winner:
            text, engine = winner[page_no]
            fell_back = False
        else:
            text, engine = fast_pages[page_no], fast_engine
            # A quarantined page is not a miss: the engine answered and we chose
            # the fast text. Counting it in both places would report one page twice
            # and read as a failure rather than a decision.
            fell_back = page_no in asked_about and page_no not in quarantined
            if fell_back:
                fallbacks.append(page_no)
        counts[engine] = counts.get(engine, 0) + 1
        karar = kararlar.get(page_no)
        merged.append(MergedPage(
            page_no=page_no, text=text or "", engine=engine,
            decision=list(decisions.get(page_no, [])), fell_back=fell_back,
            fast_skor=karar.fast_skor if karar else None,
            heavy_skor=karar.heavy_skor if karar else None,
            karar_gerekcesi=karar.gerekce if karar else None,
        ))

    if fallbacks:
        degraded = True
        notes.append(f"{len(fallbacks)} pages kept fast-path text after a heavy-engine miss")

    # CODEX-2026-08-18: A quarantined heavy page must not leak that engine's
    # table objects into an otherwise fast-path page.
    tables = []
    for engine, table in table_candidates:
        page = table.get("page")
        if page is None or winner.get(int(page), ("", ""))[1] == engine:
            tables.append(table)

    return MergedDocument(
        pages=merged, engine_counts=counts, engine_devices=devices,
        fallback_pages=fallbacks,
        tables=sorted(tables, key=lambda t: (t.get("page") or 0)),
        quarantined_pages=sorted(quarantined),
        degraded=degraded, notes=notes,
    )


def sayfa_basliklariyla(document: MergedDocument) -> str:
    """
    Render the merged pages as one markdown document with `# Page N` headings.

    Applied here rather than by each engine: pages come from different engines,
    and the heading has to be applied once, consistently, after they are combined.
    Each page's own headings are pushed a level down so the page heading stays the
    only level-1 one -- see nest_under_page above for why that matters.
    """
    return "\n\n".join(
        f"# Page {page.page_no}\n\n{nest_under_page(page.text).strip()}"
        for page in document.pages
    )
