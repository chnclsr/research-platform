# -*- coding: utf-8 -*-
"""
smart_router — sayfa duzeyinde PDF ayristirma yonlendirmesi.

TEK URETIM KAYNAGI (plan E21). `research/pdf-parser/` altindaki deney ve
benchmark betikleri bu paketi IMPORT eder, kopyalamaz — ayni kod iki klasore
kopyalanirsa kisa surede birbirinden kopar.

AKIS
    inspector (tum belge, ucuz)
      -> giris kapisi (sayfa bayraklari: needs_ocr / has_table / has_figure)
      -> critic (cikista, sayfa sayfa kalite)
      -> sayfa secici (yalniz sorunlu sayfalar agir motora)

Olculdu (9 belge, 261 sayfa): sayfalarin %44'u hizli yolda kaliyor.
Kapi 0,65-14,84 ms/sayfa; Docling 1.550 ms/sayfa — kapi 100+ kat ucuz.

`router.py` (17 ozellikli yapisal skor) bu pakete TASINMADI: legacy, yol
secemiyor, yalniz kuyruk onceligi icin duruyor (plan D8).
"""

from .critic import PDFCritic
from .gate import ESIK_VERSION, GirisKapisi, SayfaBayrak, kritik_mi, sayfa_secici
from .inspector import InspectorSonuc, PdfInspectorAdapter, InspectorSayfa
from .orchestrator import ROUTER_VERSION, SmartRouterHatti, kuyruk_skoru
from .pages import ardisik_bloklar, cagri_plani, api_icin, normalize

__all__ = [
    "PDFCritic", "GirisKapisi", "SayfaBayrak", "sayfa_secici", "kritik_mi",
    "ESIK_VERSION", "PdfInspectorAdapter", "InspectorSonuc", "InspectorSayfa",
    "SmartRouterHatti", "kuyruk_skoru", "ROUTER_VERSION",
    "ardisik_bloklar", "cagri_plani", "api_icin", "normalize",
]
