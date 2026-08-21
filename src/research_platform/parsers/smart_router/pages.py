#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pages.py
========
SAYFA NUMARASI TABAN NORMALIZASYONU (plan E5) ve
ARDISIK BLOK GRUPLAMASI (plan E4).

NEDEN AYRI BIR MODUL
--------------------
Hattaki her motor sayfa numarasini farkli tabandan sayiyor ve yanlis taban
HATA VERMEZ — sessizce komsu sayfayi dondurur. Olculdu: inspector'in
`extract_text_in_regions` fonksiyonu yanlis tabanla cagrildiginda hata yerine
KOMSU SAYFANIN metnini dondu.

OLCULEN TABAN TABLOSU (2026-08-18 dogrulandi)
----------------------------------------------

    API                                            taban
    ---------------------------------------------  ------------
    inspector  process_pdf                          1-tabanli
    inspector  extract_text_with_positions          1-tabanli
    inspector  pages_needing_ocr                    1-tabanli
    inspector  pages_with_tables                    1-tabanli
    inspector  pages_with_columns                   1-tabanli
    inspector  PageMarkdown.page                   *0-TABANLI*
    inspector  extract_pages_markdown(pages=[..])  *0-TABANLI*
    inspector  extract_text_in_regions              *0-TABANLI*
    Docling    convert(page_range=(a, b))           1-tabanli
    MinerU     CLI  -s / -e                        *0-TABANLI*

Yani AYNI NESNENIN icinde iki taban var: `extract_pages_markdown()` sonucunda
`PageMarkdown.page` 0-tabanli ama `pages_with_tables` 1-tabanli. Dogrulama:
taranmis 6 sayfalik belgede `pages_needing_ocr == [1,2,3,4,5,6]` (1-tabanli
olmasa maksimum 5 olurdu), `.page` degerleri ise `[0..5]`.

KURAL: bu hattin ICINDE dolasan her sayfa numarasi 1-TABANLIDIR. Motor
sinirinda cevrim yalniz buradaki fonksiyonlarla yapilir.

ARDISIK GRUPLAMA NEDEN GEREKLI (plan E4, olculdu)
--------------------------------------------------

    cagri bicimi                        toplam      sayfa basina
    ---------------------------------   ---------   ------------
    12 ardisik sayfa, tek cagri          18,56 sn       1,55 sn
    12 dagimik sayfa, 12 ayri cagri      29,28 sn       2,44 sn
    12 dagimik sayfa, tek alt-PDF        28,03 sn       2,34 sn

Cagri basina model yukleme maliyeti patlamiyor (%4 fark), ama ardisik
gruplama %36 kazandiriyor. Sayfa listesi ardisik bloklara bolunup her blok
tek cagrida gonderilmeli.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple

# --------------------------------------------------------------------------
# Taban cevrimi
# --------------------------------------------------------------------------

#: Hangi API hangi tabandan sayiyor — provenance ve testler icin
TABAN: Dict[str, int] = {
    "inspector.process_pdf": 1,
    "inspector.extract_text_with_positions": 1,
    "inspector.pages_needing_ocr": 1,
    "inspector.pages_with_tables": 1,
    "inspector.pages_with_columns": 1,
    "inspector.PageMarkdown.page": 0,
    "inspector.extract_pages_markdown.pages": 0,
    "inspector.extract_text_in_regions": 0,
    "docling.page_range": 1,
    "mineru.cli_s_e": 0,
}


def bir_tabanli(indeks: int) -> int:
    """0-tabanli indeks -> 1-tabanli sayfa numarasi."""
    return indeks + 1


def sifir_tabanli(sayfa_no: int) -> int:
    """1-tabanli sayfa numarasi -> 0-tabanli indeks."""
    if sayfa_no < 1:
        raise ValueError(f"1-tabanli sayfa numarasi 1'den kucuk olamaz: {sayfa_no}")
    return sayfa_no - 1


def normalize(deger: int, kaynak_api: str) -> int:
    """Bir API'den gelen sayfa numarasini 1-TABANLIYA cevirir.

    >>> normalize(0, "inspector.PageMarkdown.page")
    1
    >>> normalize(3, "inspector.pages_with_tables")
    3
    """
    if kaynak_api not in TABAN:
        raise KeyError(f"bilinmeyen API: {kaynak_api} (TABAN sozlugune ekle)")
    return deger + 1 if TABAN[kaynak_api] == 0 else deger


def api_icin(sayfa_no: int, hedef_api: str) -> int:
    """1-tabanli sayfa numarasini hedef API'nin tabanina cevirir."""
    if hedef_api not in TABAN:
        raise KeyError(f"bilinmeyen API: {hedef_api} (TABAN sozlugune ekle)")
    return sayfa_no - 1 if TABAN[hedef_api] == 0 else sayfa_no


# --------------------------------------------------------------------------
# Ardisik blok gruplamasi (plan E4)
# --------------------------------------------------------------------------

def ardisik_bloklar(sayfalar: Iterable[int]) -> List[Tuple[int, int]]:
    """1-tabanli sayfa listesini ardisik (baslangic, bitis) bloklarina boler.

    Bitis DAHILDIR. Tekrar eden sayfalar tekillenir, sira onemsizdir.

    >>> ardisik_bloklar([3, 4, 5, 9, 11, 12])
    [(3, 5), (9, 9), (11, 12)]
    >>> ardisik_bloklar([])
    []
    """
    sirali = sorted(set(int(s) for s in sayfalar))
    if not sirali:
        return []
    bloklar: List[Tuple[int, int]] = []
    bas = onceki = sirali[0]
    for no in sirali[1:]:
        if no == onceki + 1:
            onceki = no
            continue
        bloklar.append((bas, onceki))
        bas = onceki = no
    bloklar.append((bas, onceki))
    return bloklar


def blok_maliyeti(bloklar: Sequence[Tuple[int, int]]) -> Dict[str, int]:
    """Gruplamanin ne kazandirdigini gosterir (cagri sayisi ve sayfa sayisi)."""
    sayfa = sum(b - a + 1 for a, b in bloklar)
    return {"cagri": len(bloklar), "sayfa": sayfa,
            "en_uzun_blok": max((b - a + 1 for a, b in bloklar), default=0)}


# --------------------------------------------------------------------------
# Motor sinirindaki cagri argumanlari — taban cevrimi TEK NOKTADA
# --------------------------------------------------------------------------

def inspector_pages(sayfalar: Iterable[int]) -> List[int]:
    """1-tabanli liste -> `extract_pages_markdown(pages=...)` icin 0-tabanli.

    inspector dagimik listeyi kabul ediyor; gruplama gerekmez. Olculdu:
    `pages=[3,5,40]` 119 ms yerine 23 ms.

    >>> inspector_pages([1, 3, 6])
    [0, 2, 5]
    """
    return [api_icin(int(s), "inspector.extract_pages_markdown.pages")
            for s in sorted(set(int(x) for x in sayfalar))]


def docling_page_range(blok: Tuple[int, int]) -> Tuple[int, int]:
    """Ardisik blok -> Docling `convert(page_range=(a, b))`. Docling 1-tabanli.

    Docling ardisik ARALIK ister, dagimik liste kabul etmez; bu yuzden
    `ardisik_bloklar()` ile bolunmus her blok ayri cagri olur.

    >>> docling_page_range((3, 5))
    (3, 5)
    """
    a, b = blok
    return (api_icin(a, "docling.page_range"), api_icin(b, "docling.page_range"))


def mineru_args(blok: Tuple[int, int]) -> List[str]:
    """Ardisik blok -> MinerU CLI argumanlari. MinerU 0-TABANLI.

    UYARI: `-s`/`-e` bayraklarinin varligi dogrulandi ama KOSTURULMADI
    (plan 6.5). Entegre etmeden once tek sayfalik bir belgede sinanmali.

    >>> mineru_args((3, 5))
    ['-s', '2', '-e', '4']
    """
    a, b = blok
    return ["-s", str(api_icin(a, "mineru.cli_s_e")),
            "-e", str(api_icin(b, "mineru.cli_s_e"))]


def cagri_plani(sayfalar: Iterable[int], motor: str) -> Dict[str, object]:
    """Secilen sayfa listesi icin motora ozel cagri planini kurar.

    motor: "inspector" | "docling" | "mineru"
    """
    sirali = sorted(set(int(s) for s in sayfalar))
    if motor == "inspector":
        return {"motor": motor, "cagri_sayisi": 1 if sirali else 0,
                "argumanlar": [{"pages": inspector_pages(sirali)}] if sirali else [],
                "not": "dagimik liste destekleniyor, gruplama gerekmez"}

    bloklar = ardisik_bloklar(sirali)
    if motor == "docling":
        arg = [{"page_range": docling_page_range(b)} for b in bloklar]
    elif motor == "mineru":
        arg = [{"cli": mineru_args(b)} for b in bloklar]
    else:
        raise ValueError(f"bilinmeyen motor: {motor}")

    return {"motor": motor, "cagri_sayisi": len(bloklar), "argumanlar": arg,
            "bloklar": bloklar, "maliyet": blok_maliyeti(bloklar),
            "not": "ardisik aralik gerekiyor; gruplama %36 kazandiriyor (olculdu)"}


if __name__ == "__main__":
    import doctest
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sonuc = doctest.testmod(verbose=False)
    print(f"doctest: {sonuc.attempted} sinama, {sonuc.failed} basarisiz")

    ornek = [3, 4, 5, 9, 11, 12, 40]
    print(f"\nornek secili sayfalar (1-tabanli): {ornek}")
    for motor in ("inspector", "docling", "mineru"):
        p = cagri_plani(ornek, motor)
        print(f"  {motor:<10} cagri {p['cagri_sayisi']}  ->  {p['argumanlar']}")
