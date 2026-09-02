"""Deterministic similarity signals shared by claim and report quality gates."""

from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_NUMBER_RE = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?%?")
_NEGATIONS = {
    "değil", "hayır", "olmayan", "olmadı", "olmaz", "yok", "no", "not", "never",
    "neither", "without", "unchanged", "failed", "failure",
}


def normalise_text(text: str) -> str:
    return " ".join(_TOKEN_RE.findall((text or "").casefold()))


def word_counts(text: str) -> Counter[str]:
    return Counter(normalise_text(text).split())


def word_cosine(left: str, right: str) -> float:
    left_counts = word_counts(left)
    right_counts = word_counts(right)
    if not left_counts or not right_counts:
        return 0.0
    numerator = sum(value * right_counts[token] for token, value in left_counts.items())
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def sequence_ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, normalise_text(left), normalise_text(right)).ratio()


def ngram_jaccard(left: str, right: str, *, size: int = 3) -> float:
    def ngrams(value: str) -> set[tuple[str, ...]]:
        words = normalise_text(value).split()
        if len(words) < size:
            return {tuple(words)} if words else set()
        return {tuple(words[index:index + size]) for index in range(len(words) - size + 1)}

    left_ngrams = ngrams(left)
    right_ngrams = ngrams(right)
    union = left_ngrams | right_ngrams
    return len(left_ngrams & right_ngrams) / len(union) if union else 0.0


def vector_cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def number_signature(text: str) -> tuple[str, ...]:
    return tuple(match.group(0).replace(",", ".") for match in _NUMBER_RE.finditer(text or ""))


def negation_signature(text: str) -> frozenset[str]:
    return frozenset(set(normalise_text(text).split()) & _NEGATIONS)


def claim_guard_compatible(left: str, right: str) -> bool:
    """Block merges that could reverse or numerically blur a proposition."""
    return number_signature(left) == number_signature(right) and negation_signature(
        left
    ) == negation_signature(right)


def claim_duplicate_reason(
    left: str,
    right: str,
    *,
    left_vector: list[float] | None = None,
    right_vector: list[float] | None = None,
    same_passage: bool = False,
    quote_similarity: float = 0.0,
) -> tuple[str, float]:
    """Return the strongest passing signal, or an empty reason for distinct claims."""
    if not claim_guard_compatible(left, right):
        return "", 0.0
    character = sequence_ratio(left, right)
    lexical = word_cosine(left, right)
    semantic = vector_cosine(left_vector or [], right_vector or [])
    if character >= 0.92:
        return "normalised_text", character
    if same_passage and quote_similarity >= 0.65:
        return "same_passage_quote", quote_similarity
    if semantic >= 0.90 and lexical >= 0.55:
        return "embedding_and_words", semantic
    if lexical >= 0.82:
        return "word_cosine", lexical
    return "", 0.0


def prose_overlaps(left: str, right: str) -> bool:
    """Reader-visible duplication gate used after synthesis."""
    return (
        word_cosine(left, right) >= 0.82 and ngram_jaccard(left, right) >= 0.28
    ) or sequence_ratio(left, right) >= 0.90
