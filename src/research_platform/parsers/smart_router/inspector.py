#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inspector.py
============
Hızlı yolun (pdf-inspector) adaptörü.

Önceki sürüm PyMuPDF `get_text("text")` düz metnini döndürerek inspector'ı
simüle ediyordu. Düz metinde her fiziksel satır ayrı bir satırdır; critic bunu
kırık paragraf sayar. Ceza belgenin kalitesinden değil girdinin biçiminden
geliyordu (plan 1.2-b). Bu modül artık gerçek parser'ı çağırır (plan D1).

Canonical API `extract_pages_markdown` (plan D9). Sayfa bazlı critic bunu
gerektiriyor; `process_pdf().markdown` ile arasında ölçülmüş %0,01–1,52 fark
var, dolayısıyla iki yol birbirinin yerine kullanılamaz.

SAYFA NUMARASI TABANI — ölçüldü (2026-08-18), aynı sonuç nesnesinde İKİ TABAN:

    PageMarkdown.page        -> 0-tabanlı   (6 sayfalık belgede 0..5)
    extract_pages_markdown(pages=[...])  -> 0-tabanlı
    pages_needing_ocr        -> 1-tabanlı   (taranmış 6 sayfada [1..6])
    pages_with_tables        -> 1-tabanlı   (vgg: markdown tablo sayfalarının +1'i)
    pages_with_columns       -> 1-tabanlı   (6 sayfalık belgede max 6)

Karıştırılması hata vermez, sessizce komşu sayfayı döndürür. Bu modülün
DIŞINA çıkan her sayfa numarası 1-tabanlıdır (plan E5).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

import pymupdf as fitz

try:
    import pdf_inspector
    _IMPORT_HATASI: Optional[BaseException] = None
except ImportError as exc:  # opsiyonel bağımlılık
    pdf_inspector = None
    _IMPORT_HATASI = exc

#: Paket `__version__` dışa vermiyor (2026-08-20'de doğrulandı, `pdf_inspector.__version__`
#: yok) -- kurulum meta verisinden okunuyor. `health()`'in yalnız "kurulu mu"
#: değil "hangi sürüm" diyebilmesi için: pyproject.toml artık `pdf-inspector==1.14.1`'e
#: sabitliyor, ama pin'in kendisi çalışma anında neyin fiilen yüklendiğini
#: garanti etmez -- health bunu görünür kılar.
def _kurulu_surum() -> Optional[str]:
    if pdf_inspector is None:
        return None
    try:
        import importlib.metadata as _metadata  # noqa: PLC0415
        return _metadata.version("pdf-inspector")
    except Exception:
        return "bilinmeyen"

# Parser profilleri. Fallback sessiz olmaz; hangi yoldan geldiği provenance'a
# yazılabilsin diye çıktı bu adlarla etiketlenir (plan E6).
PROFIL_INSPECTOR = "inspector_v1"
PROFIL_FALLBACK = "pymupdf_fallback_v1"


def bir_tabanli(sayfa_indeksi: int) -> int:
    """0-tabanlı indeksi 1-tabanlı sayfa numarasına çevirir."""
    return sayfa_indeksi + 1


def sifir_tabanli(sayfa_no: int) -> int:
    """1-tabanlı sayfa numarasını 0-tabanlı indekse çevirir."""
    return sayfa_no - 1


@dataclass
class InspectorSayfa:
    """Tek sayfanın çıktısı. `sayfa_no` DAİMA 1-tabanlıdır."""
    sayfa_no: int
    markdown: str
    needs_ocr: bool = False
    ocr_reason: Optional[str] = None


@dataclass
class InspectorSonuc:
    """Belge çıktısı. Bütün sayfa numarası listeleri 1-tabanlıdır."""
    pdf_path: str
    profil: str
    pages: List[InspectorSayfa] = field(default_factory=list)
    pages_needing_ocr: List[int] = field(default_factory=list)
    pages_with_tables: List[int] = field(default_factory=list)
    pages_with_columns: List[int] = field(default_factory=list)
    hata: Optional[str] = None

    @property
    def text(self) -> str:
        """Sayfaların birleştirilmiş markdown'ı.

        `# Page N` başlığı BURADA eklenmez; sayfa bazlı hatta farklı sayfalar
        farklı motorlardan geleceği için sarmalayıcı birleştirme sonrası tek
        noktada uygulanmalı (plan E7).
        """
        return "\n\n".join(s.markdown for s in self.pages)


class PyMuPDFFallback:
    """pdf-inspector yoksa kullanılan yedek yol — profil `pymupdf_fallback_v1`.

    DÜZ METİN döndürür, markdown değil. Critic eşikleri bu iki girdide farklı
    davranır (plan D12), bu yüzden çıktı ayrı profil adıyla etiketlenir.
    """

    @staticmethod
    def extract_pages(pdf_path: str,
                      pages: Optional[Sequence[int]] = None) -> InspectorSonuc:
        """`pages` 1-tabanlı sayfa numaraları listesidir (None = tüm belge)."""
        sonuc = InspectorSonuc(pdf_path=pdf_path, profil=PROFIL_FALLBACK)
        if not os.path.exists(pdf_path):
            sonuc.hata = "dosya yok"
            return sonuc

        istenen = set(pages) if pages is not None else None
        try:
            doc = fitz.open(pdf_path)
            for i, page in enumerate(doc):
                no = bir_tabanli(i)
                if istenen is not None and no not in istenen:
                    continue
                sonuc.pages.append(InspectorSayfa(sayfa_no=no,
                                                  markdown=page.get_text("text")))
            doc.close()
        except Exception as exc:
            sonuc.pages = []
            sonuc.hata = f"{type(exc).__name__}: {exc}"
        return sonuc

    @staticmethod
    def extract_text(pdf_path: str) -> str:
        return PyMuPDFFallback.extract_pages(pdf_path).text


# Geriye dönük ad: eski ölçüm betikleri (src/critic_olc.py) mock ile gerçek
# çıktıyı karşılaştırabilmek için bu yolu hâlâ çağırabilmeli.
PDFInspectorMock = PyMuPDFFallback


class PdfInspectorAdapter:
    """Gerçek pdf-inspector çağrısı; yoksa adlandırılmış PyMuPDF yedeği."""

    @staticmethod
    def available() -> bool:
        return pdf_inspector is not None

    @staticmethod
    def import_hatasi() -> Optional[str]:
        return None if _IMPORT_HATASI is None else str(_IMPORT_HATASI)

    @staticmethod
    def surum() -> Optional[str]:
        """Kurulu pdf-inspector sürümü, kurulu değilse None (plan CLAUDE-2026-08-20)."""
        return _kurulu_surum()

    @staticmethod
    def extract_pages(pdf_path: str,
                      pages: Optional[Sequence[int]] = None) -> InspectorSonuc:
        """Sayfa bazlı markdown çıkarır.

        `pages`: 1-TABANLI sayfa numaraları (None = tüm belge). Kütüphaneye
        0-tabanlıya çevrilerek geçilir; dönen numaralar tekrar 1-tabanlıya
        normalize edilir.
        """
        if not os.path.exists(pdf_path):
            return InspectorSonuc(pdf_path=pdf_path, profil=PROFIL_INSPECTOR,
                                  hata="dosya yok")

        if pdf_inspector is None:
            return PyMuPDFFallback.extract_pages(pdf_path, pages)

        istenen_0 = None if pages is None else [sifir_tabanli(n) for n in pages]
        try:
            ham = pdf_inspector.extract_pages_markdown(pdf_path, pages=istenen_0)
        except Exception as exc:
            yedek = PyMuPDFFallback.extract_pages(pdf_path, pages)
            yedek.hata = f"inspector hatası, yedeğe düşüldü: {type(exc).__name__}: {exc}"
            return yedek

        sonuc = InspectorSonuc(pdf_path=pdf_path, profil=PROFIL_INSPECTOR)
        for p in ham.pages:
            sonuc.pages.append(InspectorSayfa(
                sayfa_no=bir_tabanli(p.page),          # .page 0-tabanlı
                markdown=p.markdown or "",
                needs_ocr=bool(getattr(p, "needs_ocr", False)),
                ocr_reason=getattr(p, "ocr_reason", None),
            ))
        # Bu üç liste kütüphanede ZATEN 1-tabanlı; çevrilmez.
        sonuc.pages_needing_ocr = list(ham.pages_needing_ocr or [])
        sonuc.pages_with_tables = list(ham.pages_with_tables or [])
        sonuc.pages_with_columns = list(ham.pages_with_columns or [])
        return sonuc

    @staticmethod
    def extract_text(pdf_path: str) -> str:
        return PdfInspectorAdapter.extract_pages(pdf_path).text
