#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate.py
=======
GIRIS KAPISI (plan E2) ve SAYFA SECICI (plan E3).

Kapi sayfa basina UC bayrak uretir — `needs_ocr` · `has_table` · `has_figure` —
ve SKOR URETMEZ. Yol secimini bayraklar yapar; yapisal skorun isi yalniz kuyruk
onceligidir (plan D8).

OLCULMUS KURALLAR — burada elle secilmis bir sey yok
----------------------------------------------------
Iki korpusta olculdu: kendi korpusumuz 261 sayfa (gumus referans: Docling ve
MinerU'nun anlastigi sayfalar) ve resmi benchmark 200 sayfa (ELLE etiketli
referans). Iki deger su sirayla: kendi korpus / benchmark.

  tablo    inspector `pages_with_tables` OR PyMuPDF v2 kurali (sekil vetolu,
           dolu_dikdortgen esigi 60 -- 2026-08-20 duzeltmesi)
           duyarlilik 0,93 / 0,95      kesinlik 0,64 / 0,56
           (DUZELTME ONCESI: duyarlilik 0,93 / 0,98, kesinlik 0,55 / 0,51)
           yuksek guven = inspector AND v2   kesinlik 0,75 / 0,87 (eski olcum)

  sekil    `cluster_drawings()` OR `get_images(full=True)`
           duyarlilik 0,99 / 0,99      kesinlik 0,69 / 0,62
           ESKI KURAL (bezier + kaplama) 0,63 / 0,76 idi — plan D11 uyarinca
           degistirildi.

  vektorel sekil   yalniz `cluster_drawings()`
           duyarlilik 0,97 / 0,93      kesinlik 0,48 / 0,23
           (eski kural 0,27 / 0,40)

  OCR      inspector `pages_needing_ocr`
           taranmis belgede 6/6 sayfa, kalan 255 sayfada 0 yanlis alarm

Toplam kapi maliyeti 12-18 ms/sayfa. Docling 3,6 sn/sayfa, MinerU 5,3 sn/sayfa
— kapi 200-400 kat ucuz.

SABITLENMEYENLER (plan E2): cizim vetosu ve `find_tables` hakemligi. Ikisi de
bir korpusta kazandirip digerinde kaybettirdi; kural olarak GOMULMEDI,
kalibrasyona birakildi.

DETERMINIZM (plan bolum 8.3 — kod okumasiyla dogrulandi)
--------------------------------------------------------
`registry.py`: "the same bytes have to yield the same parser on every run",
`acquisition.py`: `content_hash = sha256(normalized parsed text)`.

Bu yuzden `yuksek_guven_yeter` bir CALISMA ANI BUTCE anahtari DEGILDIR.
Kalibrasyon surumune (`esik_version`) baglidir ve bir kosu boyunca sabittir.
Bunu yuk/butceye baglamak ayni baytlarin farkli hash uretmesine yol acardi:
yeniden isleme, tekrar tespiti ve onbellek bozulur.

SAYFA NUMARALARI 1-TABANLIDIR (plan E5). inspector'in listeleri zaten
1-tabanli, `PageMarkdown.page` ise 0-tabanli — normalizasyon inspector.py'de.
"""

from __future__ import annotations

import unicodedata as ud
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pymupdf

from .ayarlar import AYAR
from .inspector import InspectorSonuc, PdfInspectorAdapter, PROFIL_INSPECTOR

# --------------------------------------------------------------------------
# ESIKLER — degerler `config/smart_router.yaml` icinde, gomulu varsayilanlar
# `ayarlar.VARSAYILAN` altinda. Kalibrasyon (plan D12) profil dosyasindan
# yapilir; burada yalniz etkin profile bakilir, sayi yazilmaz.
# --------------------------------------------------------------------------
#: Kopya: `AYAR` dondurulmus, ama tasidigi sozluk degil. Kopyalamazsak burada
#: yapilan bir degisiklik etkin profili de degistirir ve `esik_version` yalan olur.
ESIK: Dict[str, float] = dict(AYAR.kapi_esikleri)

#: Kalibrasyon surumu — provenance'a yazilir (plan E8). ELLE YAZILMAZ: etkin
#: ayarlarin sha256'sindan turetilir, boylece bir esik degisip surum ayni
#: kalamaz. Bkz. `ayarlar._surum()`.
ESIK_VERSION = AYAR.esik_version

#: Sayfa basina kac kutu saklanir. Kutular zaten hesaplaniyordu ve atiliyordu;
#: hepsini tutmak kapi butcesini degil (8,16 ms/sayfa) provenance boyutunu bozar.
#: En buyuk birkac tanesi bolge isi icin yeterli, kalani gurultu.
KUTU_SINIR = 8


def _kutu(rect) -> List[float]:
    """PyMuPDF dikdortgeni -> [x0, y0, x1, y1], sol-ust orijinli, 1 ondalik.

    PyMuPDF sayfa koordinati sol-ust orijinlidir. Docling'in bbox'i olcuye gore
    BOTTOMLEFT de olabiliyor (olculdu: turkce_makale s.3'te tablo BOTTOMLEFT,
    hucre TOPLEFT) -- iki kaynagin kutulari karistirilmadan once tabani cevrilmeli.
    """
    return [round(rect.x0, 1), round(rect.y0, 1), round(rect.x1, 1), round(rect.y1, 1)]


def _en_buyukler(dikdortgenler, alan: float) -> List[Any]:
    """Alanca en buyuk `KUTU_SINIR` dikdortgen, buyukten kucuge."""
    return sorted(dikdortgenler, key=lambda r: r.width * r.height,
                  reverse=True)[:KUTU_SINIR]


# --------------------------------------------------------------------------
# A10 — `critical_issue` KRITIK mi UYARI mi (plan 3.1-3)
# --------------------------------------------------------------------------
# Eski BELGE duzeyi `critic.evaluate()` su kosulu kullaniyordu:
#     quality_score < esik  OR  critical_issue != "NONE"
# Sayfa yoluna gecerken ikinci kosul DUSTU; `sayfa_secici` yalniz skora bakiyordu.
#
# OLCULDU (261 sayfa, out/a_kolu_kosu.json):
#     TWO_COLUMN_CROSS_JUMP        60 sayfa  ->  3'u hizli yolda kaliyordu
#     TOTAL_TEXT_DROPPED            8 sayfa  ->  0
#     CID_FONT_UNICODE_CORRUPTION   2 sayfa  ->  0
# Yani kacak gercek ama kucuk: 261 sayfada 3 sayfa (%1,1).
#
# Bu yuzden "kritik olan her sey tetiklesin" UYGULANMADI. `TWO_COLUMN_CROSS_JUMP`
# eski plan 6.4'te zaten YANLIS ALARM SUPHELISI (`attention_tablo` tek sutunlu
# bir makale oldugu halde isaretlenmisti); tetikleyici yapmak 60 sayfayi agir
# hatta iter, karsiligi olculmedi.
#
# KRITIK  = metin gercekten kayip/bozuk; agir hatti tetikler
# UYARI   = supheli ama olculmemis; yalniz provenance'a yazilir
KRITIK_TETIKLEYICI = frozenset({
    "TOTAL_TEXT_DROPPED",            # sayfada <30 karakter, gorsel/cizim var
    "SCANNED_NEEDS_OCR",             # zaten needs_ocr kapisindan da geciyor
    "CID_FONT_UNICODE_CORRUPTION",   # inspector 461 sayfada 0 uretti; vurus anlamli
    "MATH_FORMULA_HEAVY",            # eski evaluate() ile ayni; korpusta HIC tetiklenmedi
})

#: Tetiklemez, yalniz kaydedilir. Kalibrasyonda (C2) yeniden bakilacak.
UYARI = frozenset({
    "TWO_COLUMN_CROSS_JUMP",         # 60 sayfa, yanlis alarm suphesi (plan 6.4)
    "HEADER_FOOTER_BLEED",
    "BOS_SAYFA",                     # zaten secicide ayrica eleniyor
})


def kritik_mi(critical_issue: Optional[str]) -> bool:
    """`critical_issue` agir hatti tetiklemeli mi.

    `TEXT_DROPPED_GAP_37%` gibi degerler onek olarak uretiliyor
    (`critic.sayfa_skoru`), bu yuzden tam esitlik yetmez.
    """
    if not critical_issue or critical_issue == "NONE":
        return False
    if critical_issue.startswith("TEXT_DROPPED_GAP_"):
        return True
    return critical_issue in KRITIK_TETIKLEYICI


@dataclass
class SayfaBayrak:
    """Tek sayfanin kapi ciktisi. `sayfa_no` 1-TABANLI."""
    sayfa_no: int
    needs_ocr: bool = False
    has_table: bool = False
    has_figure: bool = False
    has_vector_figure: bool = False
    bos: bool = False
    #: "yuksek" = inspector AND v2 (kesinlik 0,75/0,87) · "dusuk" = yalniz biri
    tablo_guven: Optional[str] = None
    #: hangi sinyal tetikledi — provenance (plan E8)
    kaynak: Dict[str, Any] = field(default_factory=dict)

    def sozluk(self) -> Dict[str, Any]:
        return {
            "needs_ocr": self.needs_ocr,
            "has_table": self.has_table,
            "has_figure": self.has_figure,
            "has_vector_figure": self.has_vector_figure,
            "bos": self.bos,
            "tablo_guven": self.tablo_guven,
            "kaynak": self.kaynak,
        }


def _v2_tablo_karari(cizim: Dict[str, int], izgara: Dict[str, int],
                     kume_kaplama: float, esik: Dict[str, float]) -> bool:
    """PyMuPDF v2 tablo kurali -- saf fonksiyon, PyMuPDF sayfasi gerektirmez.

    UYGULANDI (2026-08-20): sekil vetosu. Sayfa buyuk bir sekil/diyagramsa
    (kume_kaplama >= sekil_veto_kaplama), ortogonal_cizgi tablo sinyaline HIC
    katilmaz -- olculdu (261 + 200 sayfa), FP'lerin cogu tam da buyuk
    diyagramlarda ortogonal_cizgi'nin 6'dan 4714'e kadar cikmasindan
    geliyordu. dolu_dikdortgen ise vetolanmiyor, cunku yogun dolu dikdortgen
    gercek tablo hucresi de olabiliyor (benchmark'ta 2 sayfada 66-105 dolu,
    gercek tablo) -- onun yerine esigi 8'den 60'a yukselttik
    (config/smart_router.yaml).

    CLAUDE-2026-08-20: `sekil_veto_kaplama > 0` sarti bilerek var. Onsuz,
    veto "kapali" (0.0) sayildiginda bile cizimsiz bir sayfada
    (kume_kaplama=0.0) `0.0 >= 0.0` True doner ve veto -- kapali olmasi
    gerekirken -- yine de ortogonal_cizgi'yi bastirirdi. Kod incelemesiyle
    bulundu, hicbir olculmus sayida bu hatanin izi yoktu cunku bugune kadar
    esik hep pozitifti.
    """
    buyuk_sekil = (esik["sekil_veto_kaplama"] > 0
                  and kume_kaplama >= esik["sekil_veto_kaplama"])
    ortogonal_gecerli = (
        not buyuk_sekil and cizim["ortogonal_cizgi"] >= esik["ortogonal_cizgi"]
    )
    return bool(
        ortogonal_gecerli
        or cizim["dolu_dikdortgen"] >= esik["dolu_dikdortgen"]
        or (izgara["izgara_sutun"] >= esik["izgara_sutun"]
            and izgara["izgara_satir"] >= esik["izgara_satir"])
    )


class GirisKapisi:
    """Sayfa basina bayrak uretir. Skor uretmez (plan E2)."""

    def __init__(self, esik: Optional[Dict[str, float]] = None) -> None:
        self.esik = dict(ESIK)
        if esik:
            self.esik.update(esik)

    # ------------------------------------------------------------ PyMuPDF v2
    def _cizim(self, page) -> Dict[str, int]:
        ortogonal = bezier = dolu = 0
        for draw in page.get_drawings():
            if draw.get("fill") is not None:
                dolu += 1
            for item in draw["items"]:
                if item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p1.x - p2.x) < 1.0 or abs(p1.y - p2.y) < 1.0:
                        ortogonal += 1
                elif item[0] == "c":
                    bezier += 1
        return {"ortogonal_cizgi": ortogonal, "bezier_egri": bezier,
                "dolu_dikdortgen": dolu}

    def _izgara(self, page) -> Dict[str, int]:
        """Kuralsiz tabloyu yakalayan sinyal: genis bosluklu hucre bandi.

        `get_text("words")` kullanilir — `get_text("dict")`ten 20 kat ucuz
        (olculdu: GPT-3 75 sayfa, dict 2.053 ms / words 111 ms).

        Iki sutunlu makale govdesi bu kurali tetiklemez: govde satirinda
        kelime arasi bosluk tek bosluk genisligindedir, sutunlar arasi bosluk
        ise satir basina yalnizca bir kez gecer (2 hucre < 3).
        """
        kelimeler = page.get_text("words")
        if not kelimeler:
            return {"izgara_sutun": 0, "izgara_satir": 0}

        ytol = self.esik["izgara_y_tolerans"]
        bosluk = self.esik["izgara_bosluk"]

        satirlar: Dict[int, List[tuple]] = {}
        for x0, y0, x1, y1, *_ in kelimeler:
            satirlar.setdefault(int(y0 / ytol), []).append((x0, x1))

        en_cok_hucre = en_uzun_bant = suanki = 0
        for anahtar in sorted(satirlar):
            kelime = sorted(satirlar[anahtar])
            hucre = 1
            onceki_sag = kelime[0][1]
            for x0, x1 in kelime[1:]:
                if x0 - onceki_sag > bosluk:
                    hucre += 1
                onceki_sag = max(onceki_sag, x1)
            en_cok_hucre = max(en_cok_hucre, hucre)
            if hucre >= self.esik["izgara_sutun"]:
                suanki += 1
                en_uzun_bant = max(en_uzun_bant, suanki)
            else:
                suanki = 0
        return {"izgara_sutun": en_cok_hucre, "izgara_satir": en_uzun_bant}

    # -------------------------------------------------------------- ana akis
    def bayrakla(self, pdf_path: str,
                 insp: Optional[InspectorSonuc] = None) -> Dict[int, SayfaBayrak]:
        """Belgenin her sayfasi icin bayrak uretir. Anahtar 1-TABANLI sayfa no.

        `insp`: cagiran taraf inspector'i ZATEN kosturduysa sonucunu buraya
        gecirir. Verilmezse burada kosturulur — ama o zaman ayni PDF inspector'dan
        IKI KEZ gecer, cunku `orchestrator.calistir()` zaten `extract_pages()`
        cagiriyor. Olculen kapi maliyeti (0,98-20,79 ms/sayfa) bu fazladan
        gecisi ICERIYORDU. (A9 borcu, plan 3.1-2.)
        """
        if insp is None:
            insp = PdfInspectorAdapter.extract_pages(pdf_path)
        insp_tablo = set(insp.pages_with_tables)      # zaten 1-tabanli
        insp_ocr = set(insp.pages_needing_ocr)        # zaten 1-tabanli
        insp_gercek = insp.profil == PROFIL_INSPECTOR

        sonuc: Dict[int, SayfaBayrak] = {}
        doc = pymupdf.open(pdf_path)
        try:
            for i, page in enumerate(doc):
                no = i + 1
                alan = max(page.rect.width * page.rect.height, 1.0)
                metin = page.get_text()
                karakter = len(metin.strip())

                # full=True SART: full=False ile get_image_bbox her seferinde
                # "need item of full page image list" hatasi verir ve kaplama
                # hicbir zaman gercek degeri olcmez (olculdu: taranmis BERT s.1
                # gercek kaplama 1,0, hatali kodun verdigi 0,05).
                gorseller = page.get_images(full=True)
                kaplama = 0.0
                raster_kutu: List[List[float]] = []
                for img in gorseller:
                    try:
                        bbox = page.get_image_bbox(img)
                        kaplama += (bbox.width * bbox.height) / alan
                        raster_kutu.append(_kutu(bbox))
                    except Exception:
                        kaplama += 0.05

                cizim = self._cizim(page)
                izgara = self._izgara(page) if karakter else {"izgara_sutun": 0,
                                                              "izgara_satir": 0}

                # --- D11: yeni sekil kurali. cluster_drawings OR raster gorsel
                try:
                    kumeler = page.cluster_drawings()
                except Exception:
                    kumeler = []
                en_buyuk_kume = max(
                    ((r.width * r.height) / alan for r in kumeler), default=0.0)
                # Kutular zaten hesaplandi; eskiden yalniz en buyuk kaplama orani
                # saklanip atiliyorlardi. Sayfa duzeyinde "tablo var mi" cevabi
                # verip "nerede" cevabini vermemek tablo karantinasini ve bolge
                # bazli hibridi (inspector.extract_text_in_regions) imkansiz
                # kiliyordu; kutular ucuz, en buyuk KUTU_SINIR tanesi tutuluyor.
                kume_kutu = [_kutu(r) for r in _en_buyukler(kumeler, alan)]
                kume_var = en_buyuk_kume >= self.esik["kume_kaplama"]
                raster_var = len(gorseller) > 0

                has_figure = bool(kume_var or raster_var)
                has_vector_figure = bool(kume_var)

                # --- tablo: iki kaynagin OR'u, guven kademesi ayri kaydedilir
                v2_tablo = _v2_tablo_karari(cizim, izgara, en_buyuk_kume, self.esik)
                insp_var = no in insp_tablo
                has_table = bool(insp_var or v2_tablo)
                tablo_guven = None
                if has_table:
                    tablo_guven = "yuksek" if (insp_var and v2_tablo) else "dusuk"

                # --- OCR: inspector birincil (olculdu 6/6, 0 yanlis alarm).
                # inspector yoksa v2 sezgiseline dusulur ve bu kayda gecer;
                # o yol OLCULMEDI.
                if insp_gercek:
                    needs_ocr = no in insp_ocr
                    ocr_kaynak = "inspector"
                else:
                    bozuk = sum(1 for c in metin
                                if c == "�" or ud.category(c) in ("Co", "Cs", "Cn"))
                    bozuk_oran = bozuk / max(len(metin), 1)
                    needs_ocr = bool(
                        (karakter < self.esik["sayfa_min_karakter"]
                         and kaplama >= self.esik["taranmis_kaplama"])
                        or bozuk_oran >= self.esik["bozuk_karakter_orani"])
                    ocr_kaynak = "pymupdf_yedek_OLCULMEDI"

                bos = bool(karakter < self.esik["bos_sayfa_karakter"]
                           and not gorseller
                           and not cizim["ortogonal_cizgi"]
                           and not cizim["bezier_egri"])

                sonuc[no] = SayfaBayrak(
                    sayfa_no=no,
                    needs_ocr=needs_ocr,
                    has_table=has_table,
                    has_figure=has_figure,
                    has_vector_figure=has_vector_figure,
                    bos=bos,
                    tablo_guven=tablo_guven,
                    kaynak={
                        "tablo_inspector": insp_var,
                        "tablo_v2": v2_tablo,
                        "sekil_kume": kume_var,
                        "sekil_raster": raster_var,
                        "kume_kaplama": round(en_buyuk_kume, 4),
                        "ocr_kaynak": ocr_kaynak,
                        "karakter": karakter,
                        "esik_version": ESIK_VERSION,
                        # kuyruk skoru (plan D8) icin — zaten hesaplandi,
                        # ikinci bir PDF gecisi olmasin diye burada tasiniyor
                        "ortogonal_cizgi": cizim["ortogonal_cizgi"],
                        "bezier_egri": cizim["bezier_egri"],
                        "gorsel_kaplama": round(kaplama, 4),
                        # CODEX-2026-08-18: C2 threshold sweeps need the raw
                        # observations, not only the thresholded flags.
                        "dolu_dikdortgen": cizim["dolu_dikdortgen"],
                        "izgara_sutun": izgara["izgara_sutun"],
                        "izgara_satir": izgara["izgara_satir"],
                        # Sayfa duzeyi bayrak nerede oldugunu soylemiyordu; bolge
                        # bazli is (tablo karantinasi, sekil kirpma) bunlari bekliyor.
                        "sekil_kume_kutulari": kume_kutu,
                        "sekil_raster_kutulari": raster_kutu[:KUTU_SINIR],
                    },
                )
        finally:
            doc.close()
        return sonuc


# ==========================================================================
# SAYFA SECICI  (plan E3)
# ==========================================================================

def sayfa_secici(bayraklar: Dict[int, SayfaBayrak],
                 kalite: Optional[Dict[int, Optional[float]]] = None,
                 *,
                 kalite_esik: float = AYAR.kalite_esik,
                 yuksek_guven_yeter: bool = AYAR.yuksek_guven_yeter,
                 kalite_vetosu_cizimsiz: bool = AYAR.kalite_vetosu_cizimsiz,
                 kritik: Optional[Dict[int, Optional[str]]] = None) -> Dict[str, Any]:
    """Agir motora gidecek sayfa listesini kurar.

    Kural (plan E3 + A10):
        needs_ocr UNION has_table UNION {kalite < esik} UNION {kritik teshis}

    `kritik`: sayfa -> `critical_issue`. Yalniz `kritik_mi()` True diyenler
    tetikler; `TWO_COLUMN_CROSS_JUMP` gibi UYARI'lar kaydedilir ama tetiklemez
    (gerekce modul basindaki A10 notunda, olculdu: 261 sayfada kacak 3 sayfa).

    `has_figure` TETIKLEYICI DEGILDIR. Olculdu (261 sayfa): yalniz-sekil
    sayfalarinin %39'u zaten kalite kapisindan gecmiyor (medyan kalite 91,5);
    sekil bayragini ayrica tetikleyici yapmak kendi korpusumuzda 22 sayfa (%8)
    ekliyor, karsiligini vermiyor.

    `yuksek_guven_yeter=True` iken yalniz `tablo_guven == "yuksek"` sayfalar
    tabloyla tetiklenir. Bu bir KALIBRASYON anahtaridir (`esik_version`),
    calisma ani butcesi DEGILDIR — gerekcesi modul basligindaki determinizm
    notunda (plan 8.3).

    `kalite` verilmezse kalite kapisi calismaz; o sayfalar "olculmedi" sayilir,
    0 sayilmaz.

    `kalite_vetosu_cizimsiz=True` iken, sayfa agir motora YALNIZ `low_quality`
    yuzunden gidiyorsa ve sayfada hic vektorel cizim yoksa gonderilmez. Gerekcesi
    olculdu (rapor O.13): `quality_score`'un heavy'den fayda gormeyi ongorme
    gucu ocrturk'te AUC 0,5006 -- rastgele. Ama kalite gerekcesini "burada
    gercekten karmasik bir duzen var" kosuluyla birlestirmek ayirici oluyor:
    cizimi olmayan sayfa duz metindir, agir motorun katacagi bir sey yoktur.
    Veto sayfa EKLEMEZ, yalniz geri ceker.

    Kasitli olarak sinirli: `has_table`, `needs_ocr` ya da kritik teshis
    yuzunden gelen sayfaya DOKUNMAZ -- bunlarin gerekcesi kalite skoru degil.
    Ayni ailede daha genis bir aday (`karakter < 1500 VE cizim yok`) C1'de daha
    iyi gorunuyordu (NET +1,3035) ama kendi korpusumuzda kestigi 8 cagrinin
    8'i de GEREKLI cikti ve 5 tablo kacirtti; uc korpusta birden sinanmasaydi
    yanlis kural secilecekti.
    """
    kalite = kalite or {}
    kritik = kritik or {}
    agir: List[int] = []
    sebep: Dict[int, List[str]] = {}

    for no in sorted(bayraklar):
        b = bayraklar[no]
        nedenler: List[str] = []

        if b.bos:
            # Bos sayfayi agir motora gondermenin karsiligi yok.
            sebep[no] = []
            continue

        if b.needs_ocr:
            nedenler.append("needs_ocr")

        if b.has_table:
            if not yuksek_guven_yeter or b.tablo_guven == "yuksek":
                nedenler.append("has_table_" + str(b.tablo_guven))

        q = kalite.get(no)
        if q is not None and q < kalite_esik:
            nedenler.append("low_quality")

        # A10: kritik teshis skordan BAGIMSIZ tetikler. Eski belge duzeyi
        # `evaluate()` bunu yapiyordu, sayfa yoluna gecerken dusmustu.
        ci = kritik.get(no)
        if kritik_mi(ci):
            nedenler.append("critical_" + str(ci))

        # Dusuk-fayda vetosu: yalniz kalite gerekcesi + hic vektorel cizim yok.
        # `kaynak` sozlugu gate'in ham gozlemleri; bezier_egri yoksa (eski
        # bayrak ya da farkli bir uretici) veto CALISMAZ -- eksik olcumu
        # "cizim yok" saymak sayfayi sessizce hizli yolda birakirdi.
        if (kalite_vetosu_cizimsiz and nedenler == ["low_quality"]
                and (b.kaynak or {}).get("bezier_egri") == 0):
            nedenler = []

        if nedenler:
            agir.append(no)
        sebep[no] = nedenler

    toplam = len(bayraklar)
    return {
        "agir_sayfalar": agir,
        "sebep": sebep,
        "hizli_sayfalar": [n for n in sorted(bayraklar) if n not in set(agir)],
        "ozet": {
            "toplam_sayfa": toplam,
            "agir_sayfa": len(agir),
            "agir_oran": round(len(agir) / toplam, 4) if toplam else 0.0,
            "yalniz_kalite": sum(1 for n in agir if sebep[n] == ["low_quality"]),
            "yalniz_ocr": sum(1 for n in agir if sebep[n] == ["needs_ocr"]),
            "kalite_olculmedi": sum(1 for n in bayraklar if kalite.get(n) is None),
            "esik_version": ESIK_VERSION,
            "kalite_esik": kalite_esik,
            "yuksek_guven_yeter": yuksek_guven_yeter,
            "kalite_vetosu_cizimsiz": kalite_vetosu_cizimsiz,
        },
    }


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) != 2:
        print("Kullanim: python tools/smart_router/gate.py <pdf>")
        sys.exit(1)

    b = GirisKapisi().bayrakla(sys.argv[1])
    s = sayfa_secici(b)
    print(f"PDF   : {sys.argv[1]}")
    print(f"Sayfa : {len(b)}")
    print(f"Ozet  : OCR {sum(x.needs_ocr for x in b.values())} | "
          f"tablo {sum(x.has_table for x in b.values())} | "
          f"sekil {sum(x.has_figure for x in b.values())} | "
          f"vektorel {sum(x.has_vector_figure for x in b.values())} | "
          f"bos {sum(x.bos for x in b.values())}")
    print(f"Agir hatta giden: {s['ozet']['agir_sayfa']}/{s['ozet']['toplam_sayfa']} "
          f"(kalite kapisi kapali)")
    print()
    print(f"{'sayfa':>5} {'OCR':>4} {'TABLO':>7} {'SEKIL':>6} {'VEKT':>5}  sebep")
    print("-" * 78)
    for no in sorted(b):
        x = b[no]
        print(f"{no:5d} {'X' if x.needs_ocr else '.':>4} "
              f"{(x.tablo_guven or '.'):>7} "
              f"{'X' if x.has_figure else '.':>6} "
              f"{'X' if x.has_vector_figure else '.':>5}  "
              f"{', '.join(s['sebep'][no])}")
