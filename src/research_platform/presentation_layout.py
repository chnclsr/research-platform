"""Deterministic text measurement and pagination for the PowerPoint report.

PowerPoint shrinks text to fit a box only while a person edits the file. A deck written by
python-pptx is shown exactly as written, so "shrink on overflow" never runs for a generated
report: run 01M2FYR67BS5WXFMEVY2RT1EHP shipped 5,132 characters in a box sized for ~900,
and the earlier size estimate (0.53 x font size per character) put titles over the logo.

Every text box in the report is therefore measured here, before it is placed. The deck is
set in Arial, which every Office installation carries; nothing has to be embedded, and the
metrics come from Arimo (bundled under ``fonts/``), which is metric-compatible with Arial by
design, so a Linux container measures exactly what Windows and macOS draw. The renderer never shrinks
a font to make text fit and never cuts text: overflowing prose continues on a next slide,
split at a sentence boundary.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).parent / "fonts"
FONT_NAME = "Arial"
_FONT_FILES = {False: "Arimo-Regular.ttf", True: "Arimo-Bold.ttf"}
# Glyph advances are read at this many pixels per point, so rounding in the rasteriser stays
# far below a hundredth of a point per character.
_PIXELS_PER_POINT = 20
# Lines are wrapped as if the box were this much narrower than it is. PowerPoint's own line
# breaking and kerning differ slightly from this greedy measure; wrapping early means a line
# measured here never takes one more line on screen.
WIDTH_SAFETY = 0.97

_ABBREVIATIONS = {
    "örn",
    "vb",
    "vs",
    "bkz",
    "dr",
    "prof",
    "doç",
    "yrd",
    "fig",
    "şek",
    "e.g",
    "i.e",
    "al",
    "vol",
    "no",
}
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+(?=[\"“‘'(\[]?[A-ZÇĞİÖŞÜ0-9])")


@dataclass(frozen=True)
class TextStyle:
    """How a run of text is drawn. Sizes are in points."""

    size: float
    bold: bool = False
    color: str = "242424"
    # Line height as a multiple of the font size. Written to the deck as exact line spacing,
    # so the height measured here is the height PowerPoint draws.
    leading: float = 1.25
    # Letter spacing in points, as DrawingML `spc` expects it.
    tracking: float = 0.0

    @property
    def line_height(self) -> float:
        return round(self.size * self.leading, 2)


@lru_cache(maxsize=64)
def _font(size: float, bold: bool) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        str(FONT_DIR / _FONT_FILES[bold]), size=max(1, round(size * _PIXELS_PER_POINT))
    )


def text_width(text: str, style: TextStyle) -> float:
    """Advance width of a single line in points."""
    if not text:
        return 0.0
    advance = _font(style.size, style.bold).getlength(text) / _PIXELS_PER_POINT
    return advance + style.tracking * len(text)


def _longest_prefix(word: str, style: TextStyle, width: float) -> int:
    """How many leading characters of an unbreakable word fit on one line (at least one)."""
    low, high = 1, len(word)
    while low < high:
        middle = (low + high + 1) // 2
        if text_width(word[:middle], style) <= width:
            low = middle
        else:
            high = middle - 1
    return low


def wrap(text: str, style: TextStyle, width: float) -> list[str]:
    """Break text into the lines a box of `width` points shows, greedy at spaces.

    A newline starts a new line. A word wider than the box (a URL, a long identifier) is
    broken by characters, as PowerPoint does.
    """
    usable = width * WIDTH_SAFETY
    lines: list[str] = []
    for paragraph in str(text or "").split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            if text_width(candidate, style) <= usable:
                current = candidate
                continue
            if current:
                lines.append(current)
            while text_width(word, style) > usable:
                cut = _longest_prefix(word, style, usable)
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines


def line_count(text: str, style: TextStyle, width: float) -> int:
    return len(wrap(text, style, width)) if str(text or "").strip() else 0


def text_height(text: str, style: TextStyle, width: float) -> float:
    return line_count(text, style, width) * style.line_height


def sentences(text: str) -> list[str]:
    """Split prose at sentence ends without changing a character of it.

    Joining the pieces with single spaces gives back the text with its whitespace
    normalised. An abbreviation such as "örn." does not end a sentence.
    """
    normalised = " ".join(str(text or "").split())
    if not normalised:
        return []
    pieces: list[str] = []
    start = 0
    for match in _SENTENCE_BREAK.finditer(normalised):
        before = normalised[start : match.start()]
        last_word = before.rsplit(" ", 1)[-1].rstrip(".!?…").lower()
        if last_word in _ABBREVIATIONS:
            continue
        pieces.append(before)
        start = match.end()
    pieces.append(normalised[start:])
    return [piece for piece in pieces if piece]


def fit_sentences(text: str, style: TextStyle, width: float, height: float) -> tuple[str, str]:
    """The longest run of whole sentences that fits `height`, and what is left over."""
    parts = sentences(text)
    kept = 0
    for index in range(1, len(parts) + 1):
        if text_height(" ".join(parts[:index]), style, width) <= height:
            kept = index
        else:
            break
    return " ".join(parts[:kept]), " ".join(parts[kept:])


def fit_lines(text: str, style: TextStyle, width: float, height: float) -> tuple[str, str]:
    """Split at a word boundary when not even one sentence fits an empty page."""
    lines = wrap(" ".join(str(text or "").split()), style, width)
    keep = max(1, math.floor(height / style.line_height))
    return " ".join(lines[:keep]), " ".join(lines[keep:])


@dataclass(frozen=True)
class Flow:
    """One flowing element of a slide body: a paragraph, a list item or a labelled block."""

    text: str
    style: TextStyle
    width: float
    # Space above the element when it is not the first thing on its page.
    gap_before: float = 0.0
    pad_top: float = 0.0
    pad_bottom: float = 0.0
    # A list marker ("1", "Ek A") drawn left of the text; the text column narrows by
    # `marker_width`.
    marker: str = ""
    marker_width: float = 0.0
    # A small heading drawn above the text and always kept on the same page as its first
    # lines.
    label: str = ""
    label_style: TextStyle | None = None
    label_gap: float = 4.0
    # Draw a hairline above the element; `strong_rule` for the first row of a list.
    rule: bool = False
    strong_rule: bool = False
    # Name given to the shapes drawn for this element, so format revisions can address them.
    name: str = "body"
    # Free-form values the renderer carries through pagination (a row's other columns).
    extra: dict = field(default_factory=dict)

    @property
    def text_width(self) -> float:
        return self.width - self.marker_width

    def label_height(self) -> float:
        if not self.label or self.label_style is None:
            return 0.0
        return text_height(self.label, self.label_style, self.width) + self.label_gap


@dataclass(frozen=True)
class Placed:
    flow: Flow
    text: str
    top: float
    height: float
    # A continuation of an element begun on an earlier page: drawn without marker or label.
    continued: bool


def paginate(flows: list[Flow], height: float, first_height: float | None = None) -> list[list[Placed]]:
    """Lay flows out top to bottom, starting a new page whenever the next piece would overflow.

    Text is split only between sentences; a single sentence taller than an empty page is split
    between lines. A label is never left alone at the bottom of a page.
    """
    pages: list[list[Placed]] = [[]]
    capacity = first_height if first_height is not None else height
    cursor = 0.0
    for flow in flows:
        remaining = " ".join(str(flow.text or "").split())
        continued = False
        if not remaining:
            remaining = ""
        while True:
            on_empty_page = not pages[-1]
            gap = 0.0 if on_empty_page else flow.gap_before
            label = 0.0 if continued else flow.label_height()
            overhead = gap + flow.pad_top + label + flow.pad_bottom
            available = capacity - cursor - overhead
            needed = text_height(remaining, flow.style, flow.text_width)
            if needed <= available:
                pages[-1].append(Placed(flow, remaining, cursor + gap, overhead - gap + needed, continued))
                cursor += overhead + needed
                break
            minimum = min(needed, 2 * flow.style.line_height)
            head, rest = ("", remaining)
            if available >= minimum:
                head, rest = fit_sentences(remaining, flow.style, flow.text_width, available)
                if not head and on_empty_page:
                    head, rest = fit_lines(remaining, flow.style, flow.text_width, available)
            if head:
                used = text_height(head, flow.style, flow.text_width)
                pages[-1].append(Placed(flow, head, cursor + gap, overhead - gap + used, continued))
                remaining, continued = rest, True
            elif on_empty_page:
                raise ValueError(f"{flow.name!r} cannot fit an empty page of {capacity:.0f} pt")
            pages.append([])
            capacity, cursor = height, 0.0
    return [page for page in pages if page] or [[]]
