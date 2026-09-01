"""Whether a piece of report text is in the language the report claims to be in.

Lifted out of `figure_analysis.py`, which had the only careful implementation: it knows a
short figure label carries a language (`Fig 2` is English, `Şekil 2` is Turkish) and it
counts marker words instead of guessing from length. `report_synthesis.py` had a second,
weaker copy -- `turkish >= 2 or english <= 2` -- which passed any block that contained a
little Turkish, including a Turkish paragraph with an English tail pasted onto the end. That
is the hole this module closes by having one implementation instead of two.

`foreign_sentences` is the part the block-level check could not do: a section can satisfy the
whole-text test and still carry sentences in the wrong language, and those are exactly what
readers were seeing in the Word reports.
"""

from __future__ import annotations

import re
from typing import Any


def _text(value: Any, limit: int = 500) -> str:
    rendered = " ".join(str(value or "").replace("\x00", "").split())
    return rendered[:limit].rstrip()


_ENGLISH_LANGUAGE_MARKERS = {
    "the",
    "and",
    "with",
    "from",
    "this",
    "figure",
    "fig",
    "shows",
    "show",
    "analysis",
    "data",
    "stage",
    "outcome",
    "model",
    "performance",
    "study",
    "results",
    "result",
    "accuracy",
    "diagnostic",
    "radiologist",
    "radiologists",
    "curve",
    "across",
    "compared",
    "comparison",
    "available",
    "values",
    "value",
    "only",
}

_TURKISH_LANGUAGE_MARKERS = {
    "ve",
    "ile",
    "bu",
    "bir",
    "şekil",
    "gösterir",
    "gösteren",
    "analiz",
    "veri",
    "aşama",
    "sonuç",
    "sonuçlar",
    "modelin",
    "performans",
    "çalışma",
    "doğruluk",
    "tanısal",
    "radyolog",
    "radyologlar",
    "eğri",
    "karşılaştırma",
    "karşılaştırıldığında",
    "değerler",
    "değer",
    "yalnızca",
    "olarak",
    "için",
}

_FIGURE_LABEL_RE = re.compile(
    r"^\s*(?P<label>fig(?:ure)?\.?|şekil)\s*(?P<number>\d+[A-Za-z]?)\b",
    flags=re.IGNORECASE,
)
#: Word count above which a text is prose rather than a label or an identifier.
_PROSE_WORDS = 5

_NUMBER_RE = re.compile(r"(?<![\w])\d+(?:[.,]\d+)*(?:\s*%)?")


def _report_language(language: str) -> str:
    return "tr" if language.lower().startswith("tr") else "en"


def _target_language_name(language: str) -> str:
    return "Turkish" if _report_language(language) == "tr" else "English"


def _language_matches(text: str, language: str) -> bool:
    """Conservatively accept report prose only when it matches the target language.

    Technical acronyms and numeric-only labels are language-neutral. Short figure labels are
    not: ``Fig 2`` belongs to English and ``Şekil 2`` belongs to Turkish, which closes the
    hole where the previous word-count heuristic treated ``Fig 2`` as Turkish.
    """

    rendered = _text(text, 12000)
    if not rendered:
        return False
    target = _report_language(language)
    label_match = _FIGURE_LABEL_RE.match(rendered)
    if label_match:
        label_language = (
            "tr" if label_match.group("label").casefold().startswith("şekil") else "en"
        )
        if label_language != target:
            return False
    words = re.findall(r"[^\W\d_]+", rendered.casefold(), flags=re.UNICODE)
    english = sum(word in _ENGLISH_LANGUAGE_MARKERS for word in words)
    turkish = sum(word in _TURKISH_LANGUAGE_MARKERS for word in words)
    if re.search(r"[çğıöşü]", rendered.casefold()):
        turkish += 2
    if target == "tr":
        if english > turkish:
            return False
        if turkish:
            return True
    else:
        if turkish > english:
            return False
        if english:
            return True
    # Turkish announces itself with diacritics; English has no positive mark of its own, so
    # its evidence is the absence of Turkish. Without this, ordinary English prose that
    # happens to use none of the marker words -- "Replication is needed before
    # generalisation" -- was judged foreign in an English report and sent to a translator
    # that would only paraphrase it.
    if target == "en" and not turkish and len(words) >= _PROSE_WORDS:
        return True
    # Acronyms, identifiers, and proper names are intentionally language-neutral. Longer
    # prose without any target-language signal is sent to the translator instead of being
    # assumed safe.
    return bool(words) and all(
        len(word) <= 4 or any(character.isupper() for character in token)
        for word, token in zip(words, re.findall(r"[^\W\d_]+", rendered, flags=re.UNICODE))
    )

def _normalise_number_token(token: str, text: str, start: int) -> tuple[str, bool]:
    compact = token.replace(" ", "")
    percent = compact.endswith("%") or bool(
        re.search(
            r"(?:%|percent|yüzde)\s*$",
            text[max(0, start - 10) : start],
            flags=re.IGNORECASE,
        )
    )
    compact = compact.rstrip("%")
    parts = re.split(r"[.,]", compact)
    if len(parts) == 1:
        normalized = parts[0]
    elif all(len(part) == 3 for part in parts[1:]):
        normalized = "".join(parts)
    else:
        normalized = f"{''.join(parts[:-1])}.{parts[-1]}"
    normalized = normalized.lstrip("0") or "0"
    return normalized, percent


def _number_signature(text: str) -> list[tuple[str, bool]]:
    return [
        _normalise_number_token(match.group(0), text, match.start())
        for match in _NUMBER_RE.finditer(text)
    ]


def _numbers_match(original: str, translated: str) -> bool:
    return _number_signature(original) == _number_signature(translated)


# Sentence enders, kept deliberately simple: an abbreviation split into two fragments costs
# nothing here, because each fragment is still judged on its own words.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")

# Lines that must keep their original language: a citation, a source title with its URL, or a
# verbatim quotation. Translating a paper's title makes the citation untraceable, so these are
# recognised and left alone rather than repaired.
_ATTRIBUTION_RE = re.compile(
    r"https?://|^\s*[>\-•]|^\s*(?:kaynak|source|atıf|citation|alıntı|quote)\s*[:：]",
    flags=re.IGNORECASE,
)


def is_attribution(text: str) -> bool:
    """True when the line is a citation, source title or quotation rather than prose."""
    rendered = _text(text, 2000)
    return bool(rendered) and bool(_ATTRIBUTION_RE.search(rendered))


def foreign_sentences(text: str, language: str, *, minimum_words: int = 6) -> list[str]:
    """The sentences inside `text` that are not in `language`.

    Short fragments are skipped: a three-word sentence carries too little signal, and a run
    of false positives would send correct prose to a translator that can only make it worse.
    """
    rendered = _text(text, 12000)
    if not rendered:
        return []
    foreign: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(rendered):
        candidate = sentence.strip()
        if not candidate or is_attribution(candidate):
            continue
        if len(re.findall(r"[^\W\d_]+", candidate, flags=re.UNICODE)) < minimum_words:
            continue
        if not _language_matches(candidate, language):
            foreign.append(candidate)
    return foreign


# Public names. The underscore-prefixed originals stay so the modules that already used them
# read unchanged.
text_snippet = _text
report_language = _report_language
target_language_name = _target_language_name
language_matches = _language_matches
numbers_match = _numbers_match
FIGURE_LABEL_RE = _FIGURE_LABEL_RE
