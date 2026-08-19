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


@dataclass
class MergedDocument:
    pages: List[MergedPage] = field(default_factory=list)
    #: Engine name -> how many pages it actually produced.
    engine_counts: Dict[str, int] = field(default_factory=dict)
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


def birlestir(
    fast_pages: Dict[int, str],
    *,
    fast_engine: str = "pdf-inspector",
    results: Sequence[EngineResult] = (),
    decisions: Optional[Dict[int, List[str]]] = None,
    requested: Optional[Dict[str, Sequence[int]]] = None,
    score: Optional[Callable[[str], Optional[float]]] = None,
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
    """
    decisions = decisions or {}
    requested = requested or {}

    winner: Dict[int, tuple[str, str]] = {}
    counts: Dict[str, int] = {}
    table_candidates: List[tuple[str, dict]] = []
    notes: List[str] = []
    degraded = False

    quarantined: List[int] = []
    for result in results:
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
            if not _is_improvement(score, fast_pages.get(page_no, ""), text):
                # Being expensive does not make output better. Docling was once
                # observed turning "unidirectionality constraint by using a masked
                # language model" into "unidi-eat i, a inn otlinnolns guage model"
                # on a scanned page -- overwriting blindly would have shipped that.
                quarantined.append(page_no)
                continue
            winner[page_no] = (text, result.engine)

    if quarantined:
        degraded = True
        notes.append(
            f"{len(quarantined)} pages kept fast-path text: the heavy engine scored "
            f"lower ({sorted(quarantined)})"
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
        merged.append(MergedPage(
            page_no=page_no, text=text or "", engine=engine,
            decision=list(decisions.get(page_no, [])), fell_back=fell_back,
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
        pages=merged, engine_counts=counts, fallback_pages=fallbacks,
        tables=sorted(tables, key=lambda t: (t.get("page") or 0)),
        quarantined_pages=sorted(quarantined),
        degraded=degraded, notes=notes,
    )


def _is_improvement(
    score: Optional[Callable[[str], Optional[float]]], fast: str, heavy: str
) -> bool:
    """
    Is the heavy engine's version at least as good as the one we already had?

    Unscoreable either way (no scorer, empty fast text, a grader that returns
    None) means we cannot tell, and the heavy page wins by default -- it was
    requested for a reason. Only a measured drop keeps the fast text.
    """
    if score is None or not fast.strip():
        return True
    try:
        fast_score, heavy_score = score(fast), score(heavy)
    except Exception:
        return True
    if fast_score is None or heavy_score is None:
        return True
    return heavy_score >= fast_score


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
