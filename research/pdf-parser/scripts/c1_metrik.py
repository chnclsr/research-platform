"""C1 icin hafif, bagimlilik-zorunlu-olmayan Markdown kalite metrikleri."""
from __future__ import annotations

# CODEX-2026-08-18: OCRTurk eval.py'deki NED/TEDS yon karisikligina baglanmadan
# ham metin ve yapi metriklerini ayri ayri saklayan olcum katmani.

import html
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

METRIC_VERSION = "c1_metrics_v1_2026-08-18"

_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_HTML = re.compile(r"<[^>]+>")
_PAGE = re.compile(r"(?mi)^\s*#\s+Page\s+\d+\s*$")
_FENCE = re.compile(r"```(?:[^\n]*)\n(.*?)```", re.S)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_TOKEN = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_HEADING = re.compile(r"(?m)^\s{0,3}#{1,6}\s+\S")
_EQUATION = re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]", re.S)


def duz_metin(markdown: str) -> str:
    """Markdown bicim farklarini azalt, okunabilir icerigi koru."""
    text = unicodedata.normalize("NFKC", markdown or "")
    text = _PAGE.sub(" ", text)
    text = _IMAGE.sub(r" \1 ", text)
    text = _LINK.sub(r" \1 ", text)
    text = _FENCE.sub(r" \1 ", text)
    text = _HTML.sub(" ", html.unescape(text))
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"[*_~`]", "", text)
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text


def _karakter_benzerligi(reference: str, prediction: str) -> tuple[float, str]:
    if not reference and not prediction:
        return 1.0, "empty-equal"
    if not reference or not prediction:
        return 0.0, "empty-mismatch"
    try:
        from rapidfuzz.distance import Levenshtein  # type: ignore
        return float(Levenshtein.normalized_similarity(reference, prediction)), "rapidfuzz"
    except ImportError:
        return float(SequenceMatcher(None, reference, prediction, autojunk=False).ratio()), "difflib"


def _token_f1(reference: str, prediction: str) -> float:
    ref = Counter(_TOKEN.findall(reference))
    pred = Counter(_TOKEN.findall(prediction))
    ortak = sum((ref & pred).values())
    precision = ortak / sum(pred.values()) if pred else 0.0
    recall = ortak / sum(ref.values()) if ref else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _tablo_sayisi(markdown: str) -> int:
    satirlar = (markdown or "").splitlines()
    markdown_sayisi = sum(1 for i in range(1, len(satirlar))
                           if _TABLE_SEP.match(satirlar[i]) and "|" in satirlar[i - 1])
    return markdown_sayisi + len(re.findall(r"<table\b", markdown or "", re.I))


def _sayi_benzerligi(a: int, b: int) -> float:
    return 1.0 - abs(a - b) / max(a, b, 1)


def metrikler(reference_markdown: str, prediction_markdown: str) -> dict:
    """Tum skorlar 0..1; yuksek daha iyi."""
    ref = duz_metin(reference_markdown)
    pred = duz_metin(prediction_markdown)
    karakter, algoritma = _karakter_benzerligi(ref, pred)
    token = _token_f1(ref, pred)
    uzunluk = min(len(ref), len(pred)) / max(len(ref), len(pred), 1)

    ref_tablo, pred_tablo = _tablo_sayisi(reference_markdown), _tablo_sayisi(prediction_markdown)
    ref_denklem = len(_EQUATION.findall(reference_markdown or ""))
    pred_denklem = len(_EQUATION.findall(prediction_markdown or ""))
    ref_baslik = len(_HEADING.findall(reference_markdown or ""))
    pred_baslik = len(_HEADING.findall(prediction_markdown or ""))
    yapi = sum((
        _sayi_benzerligi(ref_tablo, pred_tablo),
        _sayi_benzerligi(ref_denklem, pred_denklem),
        _sayi_benzerligi(ref_baslik, pred_baslik),
    )) / 3.0

    # Metin iki farkli gorunumle agirlikli; yapi kucuk ama gercek bir pay tasir.
    fayda = 0.45 * karakter + 0.40 * token + 0.05 * uzunluk + 0.10 * yapi
    return {
        "metric_version": METRIC_VERSION,
        "char_similarity": round(karakter, 6),
        "char_algorithm": algoritma,
        "token_f1": round(token, 6),
        "length_ratio": round(uzunluk, 6),
        "structure_similarity": round(yapi, 6),
        "utility": round(fayda, 6),
        "reference_chars": len(ref),
        "prediction_chars": len(pred),
        "reference_tables": ref_tablo,
        "prediction_tables": pred_tablo,
        "reference_equations": ref_denklem,
        "prediction_equations": pred_denklem,
        "reference_headings": ref_baslik,
        "prediction_headings": pred_baslik,
    }
