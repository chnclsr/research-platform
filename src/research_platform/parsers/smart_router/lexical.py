"""Source-backed lexical repairs for routed PDF pages.

The fast and heavy PDF engines can both drop the ``fi`` / ``fl`` part of a
Unicode presentation ligature.  PyMuPDF already extracts the source text while
the routing gate inspects each page, so that text is used as a verifier rather
than running another parser or guessing from a dictionary.

This module intentionally has a narrow contract: it only restores a ligature
that physically exists in the PDF source, has one unambiguous expansion on the
same page, and is missing from the selected parser output.  It does not perform
general spelling correction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

LEXICAL_NORMALIZER_VERSION = "source_ligature_v1"

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_ALL_LIGATURES = str.maketrans({
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
})
_REPAIRABLE_LIGATURES = frozenset({"\ufb01", "\ufb02"})
_SAFE_SPLIT = re.compile(
    r"(?:[ \t]+|-[ \t]+|[ \t]*-?[ \t]*\r?\n[ \t]*)\Z"
)


@dataclass(frozen=True)
class LexicalReference:
    """Compact, page-local reference derived from PyMuPDF source text."""

    words: frozenset[str]
    spellings: dict[str, frozenset[str]]
    ligature_index: dict[str, frozenset[str]]
    adjacent_words: frozenset[tuple[str, str]]


@dataclass(frozen=True)
class LigatureRepairResult:
    text: str
    repairs: int = 0
    single_token: int = 0
    split_token: int = 0
    ambiguous: int = 0


def expand_ligatures(text: str) -> str:
    """Expand Unicode presentation ligatures without changing other text."""

    return text.translate(_ALL_LIGATURES)


def _join_physical_wraps(text: str) -> str:
    """Join a hyphenated physical PDF line wrap for reference tokenisation."""

    return re.sub(r"(?<=[^\W\d_])-\s*\r?\n\s*(?=[^\W\d_])", "", text)


def _without_source_ligature(source_word: str, omitted_index: int) -> str:
    return "".join(
        "" if index == omitted_index else expand_ligatures(char)
        for index, char in enumerate(source_word)
    ).casefold()


def build_lexical_reference(source_text: str) -> LexicalReference:
    """Build a reference using only text already extracted by the gate."""

    source_words = [match.group(0) for match in _WORD.finditer(_join_physical_wraps(source_text))]
    expanded_words = [expand_ligatures(word) for word in source_words]

    spellings: dict[str, set[str]] = {}
    index: dict[str, set[str]] = {}
    for source_word, expanded_word in zip(source_words, expanded_words):
        lower = expanded_word.casefold()
        spellings.setdefault(lower, set()).add(expanded_word)
        for position, char in enumerate(source_word):
            if char not in _REPAIRABLE_LIGATURES:
                continue
            skeleton = _without_source_ligature(source_word, position)
            if len(skeleton) >= 3:
                index.setdefault(skeleton, set()).add(lower)

    lower_words = [word.casefold() for word in expanded_words]
    return LexicalReference(
        words=frozenset(lower_words),
        spellings={key: frozenset(value) for key, value in spellings.items()},
        ligature_index={key: frozenset(value) for key, value in index.items()},
        adjacent_words=frozenset(pairwise(lower_words)),
    )


def _candidate_case(candidate: str, before: str, reference: LexicalReference) -> str:
    letters = "".join(match.group(0) for match in _WORD.finditer(before))
    if letters.isupper():
        return candidate.upper()
    if letters[:1].isupper() and letters[1:].islower():
        return candidate[:1].upper() + candidate[1:]

    variants = sorted(reference.spellings.get(candidate, ()))
    if candidate in variants:
        return candidate
    return variants[0] if variants else candidate


def _is_wrap_continuation(text: str, matches: list[re.Match[str]],
                          position: int, reference: LexicalReference) -> bool:
    """True when this token is one half of a line-wrapped source word.

    A parser that keeps the physical line break leaves ``termi- nal`` where the
    source has ``terminal``.  Such a fragment is missing from the reference for
    that reason alone, not because a ligature was lost, and rewriting it would
    corrupt text that was already correct.  This is the same rule the split pass
    already applies -- a joined pair that the source knows as one word is left
    alone -- read from the other side.
    """

    word = matches[position].group(0)
    if position > 0:
        left = matches[position - 1]
        separator = text[left.end():matches[position].start()]
        if (_SAFE_SPLIT.fullmatch(separator)
                and (left.group(0) + word).casefold() in reference.words):
            return True
    if position + 1 < len(matches):
        right = matches[position + 1]
        separator = text[matches[position].end():right.start()]
        if (_SAFE_SPLIT.fullmatch(separator)
                and (word + right.group(0)).casefold() in reference.words):
            return True
    return False


def _apply(text: str, changes: list[tuple[int, int, str]]) -> str:
    for start, end, replacement in sorted(changes, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def repair_ligatures(text: str, reference: LexicalReference) -> LigatureRepairResult:
    """Restore source-backed ``fi`` / ``fl`` losses in one selected page.

    Both one-token losses (``predened``) and parser-created splits
    (``Arti cial`` or ``classifica- tion``) are supported.  A split is never
    joined across a blank line, and a word pair that also exists as two adjacent
    source words is left untouched.  A token the source knows only as half of a
    line-wrapped word (``termi- nal``) is left untouched as well.
    """

    split_changes: list[tuple[int, int, str]] = []
    ambiguous = 0
    matches = list(_WORD.finditer(text))
    occupied_until = -1
    for left, right in pairwise(matches):
        if left.start() < occupied_until:
            continue
        separator = text[left.end():right.start()]
        if not _SAFE_SPLIT.fullmatch(separator):
            continue
        left_word, right_word = left.group(0), right.group(0)
        if len(left_word) < 2 or len(right_word) < 2:
            continue
        pair = (left_word.casefold(), right_word.casefold())
        if pair in reference.adjacent_words:
            continue
        skeleton = (left_word + right_word).casefold()
        if skeleton in reference.words:
            continue
        candidates = reference.ligature_index.get(skeleton, frozenset())
        if len(candidates) > 1:
            ambiguous += 1
            continue
        if len(candidates) != 1:
            continue
        candidate = next(iter(candidates))
        split_changes.append((
            left.start(), right.end(),
            _candidate_case(candidate, text[left.start():right.end()], reference),
        ))
        occupied_until = right.end()

    repaired = _apply(text, split_changes)
    single_changes: list[tuple[int, int, str]] = []
    single_matches = list(_WORD.finditer(repaired))
    for position, match in enumerate(single_matches):
        before = match.group(0)
        lower = before.casefold()
        if lower in reference.words:
            continue
        if _is_wrap_continuation(repaired, single_matches, position, reference):
            continue
        candidates = reference.ligature_index.get(lower, frozenset())
        if len(candidates) > 1:
            ambiguous += 1
            continue
        if len(candidates) != 1:
            continue
        candidate = next(iter(candidates))
        single_changes.append((
            match.start(), match.end(), _candidate_case(candidate, before, reference),
        ))

    repaired = _apply(repaired, single_changes)
    return LigatureRepairResult(
        text=repaired,
        repairs=len(split_changes) + len(single_changes),
        single_token=len(single_changes),
        split_token=len(split_changes),
        ambiguous=ambiguous,
    )
