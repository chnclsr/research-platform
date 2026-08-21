"""
C1 icin korpus adaptorleri -- her veri setini AYNI kayit bicimine cevirir.

NEDEN BU MODUL VAR
------------------
C1 sorusu ("yonlendirme cikti kalitesini gercekten iyilestiriyor mu") iki ayri
seye ihtiyac duyuyor ve bunlar farkli veri setlerinden geliyor:

  * PDF + REFERANS METIN  -> cikardigimiz metni neye gore puanlayacagiz
  * sayfa basina TABLO/SEKIL etiketi -> kapiyi neye gore kalibre edecegiz (C2)

Elimizdeki uc set bunlarin farkli alt kumelerini veriyor ve ikisinde PDF hic
yok. Sessizce atlamak bu projede bir kez pahaliya patladi (pipeline.py --legacy
bos metinle cikis 0 donuyordu), o yuzden buradaki kural ayni: PDF'i olmayan set
envanterden DUSMEZ, atlama_sebebi ile birlikte GORUNUR kalir.

YETENEK SOZLUGU
---------------
Her kayit ne ise yaradigini kendisi soyler; tuketici "hangi set neydi" diye
bilmek zorunda kalmaz:

  pdf_parse        SmartPdfParser.parse(bytes) icin gercek bir PDF var
  metin_referansi  cikarilan metnin karsilastirilacagi referans metin var (C1)
  sayfa_etiketi    sayfa basina tablo/sekil/denklem sayisi var (C2 kalibrasyon)
  yalnizca_duzen   yalniz duzen kutulari var; PDF de referans metin de yok

ETIKET KAPSAMI
--------------
etiket_kapsami alani "sayfa" ya da "belge" der. Bu onemli: OCRTurk etiketleri
belge duzeyinde tutuluyor ama her belgesi TEK SAYFA oldugu icin (olculdu,
180/180) belge etiketi ayni zamanda sayfa etiketidir. Cok sayfali bir set
gelirse bu esitlik bozulur; o yuzden varsayim degil OLCUM olarak yaziliyor.

Veri setlerinin kendi dosyalarina DOKUNULMAZ; bu modul yalnizca okur.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Iterator, Optional

#: Ham veri setlerinin koku. Klon baska yerdeyse ortam degiskeniyle ez --
#: uretim_yolu.URETIM_SRC ile ayni kalip.
CALIBRATION_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.dirname(CALIBRATION_ROOT))
KORPUS_KOK = os.path.abspath(os.environ.get(
    "KORPUS_RAW",
    os.path.join(REPO_ROOT, "corpus", "raw"),
))
OPENDATALOADER_KOK = os.path.abspath(os.environ.get(
    "OPENDATALOADER_BENCH",
    os.path.join(CALIBRATION_ROOT, "corpus", "opendataloader-bench"),
))

PDF_PARSE = "pdf_parse"
METIN_REFERANSI = "metin_referansi"
SAYFA_ETIKETI = "sayfa_etiketi"
YALNIZCA_DUZEN = "yalnizca_duzen"
SAYFA_GORSELI = "sayfa_gorseli"

# CODEX-2026-08-18: Manifest tuketicilerinin alan degisikliklerini fark
# edebilmesi icin semayi acikca surumluyoruz.
MANIFEST_SCHEMA_VERSION = 2


@dataclass
class KorpusKaydi:
    """Envanterdeki tek satir. Sete degil, TEK SAYFA/BELGEYE karsilik gelir."""

    veri_seti: str
    kimlik: str
    yol_koku: str = "korpus_raw"
    yetenekler: list = field(default_factory=list)
    #: PDF yoksa neden yok. pdf_parse yetenegi olmayan her kayit bunu doldurur.
    atlama_sebebi: Optional[str] = None
    #: KORPUS_KOK'e gore goreli, POSIX ayrac. Mutlak yol makineye bagli olurdu.
    pdf_yolu: Optional[str] = None
    pdf_bayt: Optional[int] = None
    #: Ayni girdiyle kosuldugunu sonradan kanitlayabilmek icin.
    pdf_sha256: Optional[str] = None
    sayfa_sayisi: Optional[int] = None
    referans: dict = field(default_factory=dict)
    etiketler: dict = field(default_factory=dict)
    etiket_kapsami: str = "yok"
    ustveri: dict = field(default_factory=dict)
    sorunlar: list = field(default_factory=list)

    def sozluk(self) -> dict:
        return asdict(self)


def _goreli(yol: str) -> str:
    return os.path.relpath(yol, KORPUS_KOK).replace("\\", "/")


def _opendataloader_goreli(yol: str, kok: str) -> str:
    return os.path.relpath(yol, kok).replace("\\", "/")


def _sha256(yol: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(yol, "rb") as f:
            for parca in iter(lambda: f.read(1 << 20), b""):
                h.update(parca)
        return h.hexdigest()
    except OSError:
        return None


def _json_oku(yol: str) -> dict:
    """
    BOM'lu JSON'u da okur.

    OCRTurk'un 180 source.json dosyasinin 107'si UTF-8 BOM ile basliyor
    (olculdu). Duz utf-8 ile acilirsa ilk anahtar "﻿difficulty" olur ve
    .get("difficulty") sessizce None doner -- zorluk dagilimi bos cikar, hata
    verilmez. utf-8-sig BOM yoksa da calisir.
    """
    with open(yol, encoding="utf-8-sig") as f:
        return json.load(f)


def sayfa_sayisi(pdf_yolu: str) -> Optional[int]:
    """PyMuPDF yoksa None doner -- envanter yine uretilir, alan bos kalir."""
    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError:
            return None
    try:
        belge = pymupdf.open(pdf_yolu)
        try:
            return belge.page_count
        finally:
            belge.close()
    except Exception:
        return None


_MD_TABLO = re.compile(r"(?m)^\s*\|.*\|\s*$")
_HTML_TABLO = re.compile(r"<table\b", re.I)


def _referans_tablo_izi(metin: str) -> int:
    """
    Referans metinde kac tablo BLOGU gorunuyor.

    Etiketle capraz kontrol icin: count_info "3 tablo" diyorsa referans metinde
    de tablo gorunmeli. Tutmayan belge, C1'de guvenilmez referans demektir.
    Kesin tablo sayisi degil, kaba bir iz -- envanterde de oyle adlandirildi.
    """
    bloklar = 0
    onceki = False
    for satir in metin.splitlines():
        bu = bool(_MD_TABLO.match(satir))
        if bu and not onceki:
            bloklar += 1
        onceki = bu
    return bloklar + len(_HTML_TABLO.findall(metin))


class OcrTurkKaynak:
    """
    OCRTurk: PDF + referans markdown + belge basina tablo/sekil/denklem sayisi.

    C1 icin elimizdeki TEK tam kaynak -- hem parse edilebilir PDF hem metnin
    karsilastirilacagi referans ayni yerde. Ustelik Turkce, ki mevcut korpusta
    tek Turkce belge vardi.
    """

    ad = "ocrturk"

    def __init__(self, kok: Optional[str] = None, hash_hesapla: bool = True):
        self.kok = kok or os.path.join(KORPUS_KOK, "ocrturk", "data")
        self.hash_hesapla = hash_hesapla

    def mevcut(self) -> bool:
        return os.path.isdir(self.kok)

    def kayitlar(self) -> Iterator[KorpusKaydi]:
        for ad in sorted(os.listdir(self.kok), key=self._sirala):
            klasor = os.path.join(self.kok, ad)
            if not ad.startswith("data_") or not os.path.isdir(klasor):
                continue
            yield self._kayit(ad, klasor)

    @staticmethod
    def _sirala(ad: str):
        """data_2 < data_10 olsun diye -- alfabetik sira envanteri okunmaz yapar."""
        m = re.search(r"(\d+)$", ad)
        return (0, int(m.group(1))) if m else (1, 0)

    def _kayit(self, ad: str, klasor: str) -> KorpusKaydi:
        pdf = os.path.join(klasor, ad + ".pdf")
        md = os.path.join(klasor, ad + ".md")
        kayit = KorpusKaydi(veri_seti=self.ad, kimlik=ad)

        if not os.path.isfile(pdf):
            kayit.atlama_sebebi = "pdf_yok"
            return kayit

        kayit.yetenekler.append(PDF_PARSE)
        kayit.pdf_yolu = _goreli(pdf)
        kayit.pdf_bayt = os.path.getsize(pdf)
        if self.hash_hesapla:
            kayit.pdf_sha256 = _sha256(pdf)
        kayit.sayfa_sayisi = sayfa_sayisi(pdf)

        if os.path.isfile(md):
            with open(md, encoding="utf-8-sig") as f:
                metin = f.read()
            kayit.yetenekler.append(METIN_REFERANSI)
            kayit.referans = {
                "bicim": "markdown",
                "yol": _goreli(md),
                "karakter": len(metin),
                "tablo_izi": _referans_tablo_izi(metin),
            }
        else:
            kayit.referans = {"bicim": None, "not": "referans markdown yok"}

        sayim = self._belki(os.path.join(klasor, "count_info.json"))
        if sayim:
            kayit.etiketler = {
                "tablo": sayim.get("tables"),
                "sekil": sayim.get("figures"),
                "denklem": sayim.get("equations"),
            }
            # Etiket dosyasi belge duzeyinde. Tek sayfali belgede bu ayni
            # zamanda sayfa etiketidir; cok sayfaliya GENELLENEMEZ.
            if kayit.sayfa_sayisi == 1:
                kayit.etiket_kapsami = "sayfa"
                kayit.yetenekler.append(SAYFA_ETIKETI)
            else:
                kayit.etiket_kapsami = "belge"

        kaynak = self._belki(os.path.join(klasor, "source.json"))
        if kaynak:
            kayit.ustveri = {
                "zorluk": kaynak.get("difficulty"),
                "tur": kaynak.get("type"),
                "kaynak_url": kaynak.get("source"),
                "dil": "tr",
            }
        figur = os.path.join(klasor, "figures")
        if os.path.isdir(figur):
            kayit.ustveri["referans_figur"] = len(os.listdir(figur))
        return kayit

    @staticmethod
    def _belki(yol: str) -> Optional[dict]:
        if not os.path.isfile(yol):
            return None
        try:
            return _json_oku(yol)
        except (json.JSONDecodeError, OSError):
            return None


class DocLayNetKaynak:
    """
    DocLayNet ICDAR-2023 yarisma alt kumesi: PNG + duzen kutusu, PDF YOK.

    PDF olmadigi icin hattimiza girdi olamaz -- SmartPdfParser.parse() bayt
    aliyor ve altindaki her motor PDF bekliyor. PNG'yi PDF'e sarmak sentetik bir
    tarama uretir; bizde zaten sentetik tarama var, ikincisi yeni bilgi vermez.
    O yuzden kontrollu atlama: kayit gorunur kalir, atlama_sebebi="pdf_yok".

    Ne ise yarar: duzen etiketleri (Table/Picture/Formula) kapinin NE bulmasi
    gerektiginin bagimsiz bir tanimi. Sayfa goruntusu uzerinden calisan ayri bir
    dogrulama kurulursa buraya baglanir.

    OLCULEN UYARI: bu, 80.863 sayfalik tam DocLayNet DEGIL. Uc alt kume var ve
    yalniz competition_groundtruth etiketli (498 sayfa, 243 Table kutusu).
    competition_public ayni 498 sayfanin ETIKETSIZ kopyasi (dosya adlari %100
    ortusuyor -- olculdu), dev_public 20 sayfa ama belge turu etiketi yalniz
    onda var. Yani "6 belge turu cesitliligi" bu indirmede 20 sayfa demek.
    """

    ad = "doclaynet"
    #: Kapinin tahmin ettigi seylerle esleseni; digerleri ustveride kalir.
    ILGILI = {"Table": "tablo", "Picture": "sekil", "Formula": "denklem"}

    def __init__(self, kok: Optional[str] = None):
        self.kok = kok or os.path.join(KORPUS_KOK, "doclaynet_icdar")

    def mevcut(self) -> bool:
        return os.path.isdir(self.kok)

    def kayitlar(self) -> Iterator[KorpusKaydi]:
        for alt in sorted(os.listdir(self.kok)):
            coco = os.path.join(self.kok, alt, "coco.json")
            if os.path.isfile(coco):
                for kayit in self._alt_kume(alt, coco):
                    yield kayit

    def _alt_kume(self, alt: str, coco_yolu: str) -> Iterator[KorpusKaydi]:
        try:
            coco = _json_oku(coco_yolu)
        except (json.JSONDecodeError, OSError):
            return
        adlar = {k["id"]: k["name"] for k in coco.get("categories", [])}
        sayimlar: dict = {}
        for annot in coco.get("annotations") or []:
            ad = adlar.get(annot.get("category_id"))
            kova = sayimlar.setdefault(annot.get("image_id"), {})
            kova[ad] = kova.get(ad, 0) + 1
        etiketli = bool(sayimlar)

        for gorsel in coco.get("images", []):
            ham = sayimlar.get(gorsel.get("id"), {})
            gorsel_yolu = os.path.join(self.kok, alt, "PNG", gorsel["file_name"])
            kayit = KorpusKaydi(
                veri_seti=self.ad,
                kimlik=alt + "/" + os.path.splitext(gorsel["file_name"])[0],
                yetenekler=[SAYFA_GORSELI] if os.path.isfile(gorsel_yolu) else [],
                atlama_sebebi="pdf_yok",
                ustveri={
                    "alt_kume": alt,
                    "belge_turu": gorsel.get("doc_category"),
                    "kaynak_pdf": gorsel.get("doc_name"),
                    "sayfa_no": gorsel.get("page_no"),
                    "gorsel": _goreli(gorsel_yolu),
                },
            )
            if not os.path.isfile(gorsel_yolu):
                kayit.sorunlar.append("gorsel_yok")
            if etiketli:
                kayit.etiketler = {
                    yeni: ham.get(eski, 0) for eski, yeni in self.ILGILI.items()
                }
                kayit.etiketler["duzen_kutusu"] = sum(ham.values())
                kayit.etiket_kapsami = "sayfa"
                kayit.yetenekler.extend([YALNIZCA_DUZEN, SAYFA_ETIKETI])
            else:
                kayit.ustveri["not"] = "bu alt kumede duzen etiketi yok"
            yield kayit


class OmniDocBenchKaynak:
    """
    OmniDocBench: sayfa goruntusu + blok blok referans metin, PDF YOK.

    Ilk bakista C1 icin ideal gorunuyordu (referans metin var), ama indirilen
    surumde PDF yok -- yalniz PNG/JPG. Referans metin blok duzeyinde
    layout_dets[].text icinde duruyor, yani goruntu alan bir hat icin
    kullanilabilir; PDF alan bizim hattimiza dogrudan sokulamaz.

    Bu yuzden kontrollu atlama, ama kayit envanterde kaliyor: ilerde goruntu
    alan bir yol (dogrudan PNG isleyen OCR motoru) eklenirse hazir bekliyor.
    """

    ad = "omnidocbench"
    ILGILI = {"table": "tablo", "figure": "sekil", "equation_isolated": "denklem"}

    def __init__(self, kok: Optional[str] = None):
        self.kok = kok or os.path.join(KORPUS_KOK, "omnidocbench")
        self.annot = os.path.join(self.kok, "OmniDocBench.json")

    def mevcut(self) -> bool:
        return os.path.isfile(self.annot)

    def kayitlar(self) -> Iterator[KorpusKaydi]:
        try:
            veri = _json_oku(self.annot)
        except (json.JSONDecodeError, OSError, MemoryError):
            return
        for sira, sayfa in enumerate(veri):
            bilgi = sayfa.get("page_info") or {}
            nitelik = bilgi.get("page_attribute") or {}
            ham: dict = {}
            metin_uzunluk = 0
            for blok in sayfa.get("layout_dets") or []:
                tur = blok.get("category_type")
                ham[tur] = ham.get(tur, 0) + 1
                metin_uzunluk += len(blok.get("text") or "")
            gorsel = bilgi.get("image_path") or ("kayit_%d.png" % sira)
            gorsel_yolu = os.path.join(self.kok, "images", gorsel)
            kayit = KorpusKaydi(
                veri_seti=self.ad,
                kimlik=os.path.splitext(gorsel)[0],
                yetenekler=[YALNIZCA_DUZEN, SAYFA_ETIKETI]
                + ([SAYFA_GORSELI] if os.path.isfile(gorsel_yolu) else []),
                atlama_sebebi="pdf_yok",
                etiketler={
                    yeni: ham.get(eski, 0) for eski, yeni in self.ILGILI.items()
                },
                etiket_kapsami="sayfa",
                referans={
                    "bicim": "blok_metin",
                    "yol": _goreli(self.annot),
                    "karakter": metin_uzunluk,
                    "not": "PDF olmadigi icin C1'de dogrudan kullanilamaz",
                },
                ustveri={
                    "belge_turu": nitelik.get("data_source"),
                    "dil": nitelik.get("language"),
                    "duzen": nitelik.get("layout"),
                    "alt_kume": nitelik.get("subset"),
                    "sayfa_no": bilgi.get("page_no"),
                    "gorsel": _goreli(gorsel_yolu),
                },
            )
            if not os.path.isfile(gorsel_yolu):
                kayit.sorunlar.append("gorsel_yok")
            yield kayit


# CODEX-2026-08-18: Repoda zaten bulunan 200 Ingilizce PDF + ground-truth
# Markdown ciftini C1'e baglar; dosyalari corpus/raw altina kopyalamaz.
class OpenDataLoaderBenchKaynak:
    ad = "opendataloader_bench"

    def __init__(self, kok: Optional[str] = None, hash_hesapla: bool = True):
        self.kok = kok or OPENDATALOADER_KOK
        self.pdf_kok = os.path.join(self.kok, "pdfs")
        self.md_kok = os.path.join(self.kok, "ground-truth", "markdown")
        self.annot = os.path.join(self.kok, "ground-truth", "reference.json")
        self.hash_hesapla = hash_hesapla

    def mevcut(self) -> bool:
        return all(os.path.isdir(p) for p in (self.pdf_kok, self.md_kok)) and os.path.isfile(self.annot)

    def kayitlar(self) -> Iterator[KorpusKaydi]:
        annotation = _json_oku(self.annot)
        for name in sorted(os.listdir(self.pdf_kok)):
            if not name.lower().endswith(".pdf"):
                continue
            stem = os.path.splitext(name)[0]
            pdf = os.path.join(self.pdf_kok, name)
            md = os.path.join(self.md_kok, stem + ".md")
            elements = (annotation.get(name) or {}).get("elements") or []
            counts: dict = {}
            for element in elements:
                category = element.get("category")
                counts[category] = counts.get(category, 0) + 1
            record = KorpusKaydi(
                veri_seti=self.ad, kimlik=stem, yol_koku="opendataloader_bench",
                yetenekler=[PDF_PARSE], pdf_yolu=_opendataloader_goreli(pdf, self.kok),
                pdf_bayt=os.path.getsize(pdf),
                pdf_sha256=_sha256(pdf) if self.hash_hesapla else None,
                sayfa_sayisi=sayfa_sayisi(pdf),
                ustveri={"dil": "en", "tur": "benchmark_page",
                         "kaynak": "opendataloader-bench"},
            )
            if os.path.isfile(md):
                with open(md, encoding="utf-8-sig") as f:
                    text = f.read()
                record.yetenekler.append(METIN_REFERANSI)
                record.referans = {
                    "bicim": "markdown", "yol": _opendataloader_goreli(md, self.kok),
                    "karakter": len(text), "tablo_izi": _referans_tablo_izi(text),
                }
            else:
                record.sorunlar.append("referans_markdown_yok")
            if record.sayfa_sayisi == 1:
                record.yetenekler.append(SAYFA_ETIKETI)
                record.etiket_kapsami = "sayfa"
            else:
                record.etiket_kapsami = "belge"
            record.etiketler = {
                "tablo": counts.get("Table", 0),
                "sekil": counts.get("Figure", 0) + counts.get("Chart", 0),
                "denklem": counts.get("Equation", 0),
            }
            yield record


def kaynaklar(hash_hesapla: bool = True):
    """Envanterin tarayacagi butun setler, sabit sirada."""
    return (
        OcrTurkKaynak(hash_hesapla=hash_hesapla),
        DocLayNetKaynak(),
        OmniDocBenchKaynak(),
        OpenDataLoaderBenchKaynak(hash_hesapla=hash_hesapla),
    )
