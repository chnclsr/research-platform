"""pdf-inspector  vs  mevcut sistemin PDF okuyucusu  karsilastirmasi.

Uc parser yan yana calistirilir:

    pypdf_plain   page.extract_text()                      <- SISTEMDE SU AN BU VAR
                  (acquisition.py:238 ile birebir ayni)
    pypdf_layout  page.extract_text(extraction_mode="layout")
                  (pypdf'in daha iyi modu -- adil baseline)
    inspector     pdf_inspector.process_pdf()

Olculenler ikiye ayrilir:
  * satici metrikleri  : kutuphanenin kendi rapor ettigi degerler (pdf_type,
                         confidence, pages_with_columns ...) -- sadece inspector
  * kusur sayaclari    : uc cikti icin de AYNI sekilde hesaplanan hata
                         adetleri (ligatur, tireleme, sayfa mobilyasi ...).
                         Bunlar saticidan bagimsizdir, kiyas bunlara dayanir.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe compare.py
    .\\.venv\\Scripts\\python.exe compare.py --quick          # tek kosu
    .\\.venv\\Scripts\\python.exe compare.py --only bert      # tek dosya
    .\\.venv\\Scripts\\python.exe compare.py --no-layout      # layout modunu atla (yavas)

Ciktilar
--------
    out/<dosya>__pypdf_plain.md    her parser'in urettigi ham metin
    out/<dosya>__pypdf_layout.md
    out/<dosya>__inspector.md
    out/basliklar_<dosya>.txt      elle etiketlemek icin baslik listesi
    sonuclar.csv                   tum metrikler
"""
from __future__ import annotations

import csv
import io
import logging
import os
import re
import statistics
import sys
import tempfile
import time
import traceback
from collections import Counter

import pdf_inspector
import pypdf

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
CORPUS_DIR = os.path.join(BASE, "corpus")
OUT_DIR = os.path.join(BASE, "out")
CSV_PATH = os.path.join(BASE, "sonuclar.csv")

# ----------------------------------------------------------------------
# opendataloader-pdf, Java 11+ isteyen bir Java CLI'nin sarmalayicisidir.
# Sistemdeki Java 8 yetmiyor (class file version 52 < 55), bu yuzden
# tools/ altina tasinabilir bir JRE 21 indirildi. Sistem Java'sina
# DOKUNULMUYOR -- sadece bu surecin PATH'i degistiriliyor.
# ----------------------------------------------------------------------
JRE_BIN = os.path.join(BASE, "tools", "jdk-21.0.12+8-jre", "bin")
if os.path.isdir(JRE_BIN):
    os.environ["PATH"] = JRE_BIN + os.pathsep + os.environ.get("PATH", "")
    os.environ["JAVA_HOME"] = os.path.dirname(JRE_BIN)

import opendataloader_pdf  # noqa: E402  (JRE ayarindan SONRA yuklenmeli)
import pymupdf4llm  # noqa: E402

# opendataloader sayfa sinirlarini bu isaretle veriyor; olcumden once
# temizlenir, sayfa listesi bununla bolunur.
ODL_SEP = "<<<ODL_PAGE>>>"

RUNS = 3       # kosu sayisi
WARMUP = 1     # ilk kosu atilir (dosya sistemi onbellegi isinsin diye)

PARSERS = ("pypdf_plain", "pypdf_layout", "inspector", "opendataloader",
           "pymupdf4llm")


# ======================================================================
#  DESENLER
# ======================================================================

HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*)$")

# ----------------------------------------------------------------------
# research-platform/evidence_quality.py -> _NON_EVIDENCE_SECTION
#
# BURASI GERCEK REPODAKI DESENIN KOPYASI OLMALI. Repodaki desen degisirse
# burayi da guncelle, yoksa bu script yaniltici sonuc verir.
#
# Turkce karakter uyarisi: "Kaynakca" DEGIL "Kaynakça". ASCII 'c' ile
# yazilan desen gercek Turkce belgelerde hicbir sey yakalamaz.
# ----------------------------------------------------------------------
NON_EVIDENCE_RE = re.compile(
    r"(references|bibliography|works\s+cited|how\s+to\s+cite|"
    r"acknowledg(?:e)?ments?|appendix|appendices|supplementary|"
    r"kaynak[çc]a|kaynaklar|te[şs]ekk[üu]r|ekler)",
    re.IGNORECASE,
)

# Ligatur karakterleri: U+FB00-U+FB04  (ff fi fl ffi ffl)
# Bunlar cikti icinde kalirsa kelime aramasi bozulur: "different" kelimesi
# "di<U+FB00>erent" olarak yazilir ve hicbir arama eslesmez.
LIGATURE_RE = re.compile(r"[\uFB00-\uFB04]")

# Satir sonu tirelemesi birlestirilmemis:  "Universi-\ntede"  /  "Universi- tede"
HYPHEN_NEWLINE_RE = re.compile(r"\w+-\s*\n\s*\w+")
HYPHEN_INLINE_RE = re.compile(r"\w+-[ \t]+\w+")

# Ust simge dipnot isaretinin kelimeye yapismasi: "sonuclar12", "model3"
# HEURISTIK: "BERT2", "Table1" gibi mesru kullanimlari da sayar.
# Mutlak deger degil, uc parser arasindaki FARK anlamlidir.
FOOTNOTE_STICK_RE = re.compile(r"\b[A-Za-zÇĞİÖŞÜçğıöşü]{3,}\d{1,2}\b")

TURKISH_CHARS = set("çğıöşüÇĞİÖŞÜ")

# Bozuk kodlama izleri: UTF-8 baytlarinin latin-1 olarak okunmasi
MOJIBAKE_RE = re.compile(r"(Ã§|ÄŸ|Ä±|Ã¶|ÅŸ|Ã¼|Ä°|ï¿½|\ufffd)")


# ======================================================================
#  KUSUR SAYACLARI  (uc cikti icin de ayni sekilde hesaplanir)
# ======================================================================

def headings(text: str) -> list[str]:
    """Markdown baslik satirlarini dondurur."""
    return [m.group(0).strip() for m in
            (HEADING_RE.match(l) for l in text.splitlines()) if m]


def gate_check(text: str) -> tuple[bool, int, list[str]]:
    """evidence_quality kapisi bu ciktida tetiklenir mi?

    Sistemdeki kapi SADECE section_path'e bakiyor, section_path da SADECE
    Markdown basliklarindan uretiliyor. Bu yuzden govde metnine bakmiyoruz --
    "REFERENCES" duz metin olarak gecse bile kapi tetiklenmez.
    """
    hits = [h for h in headings(text) if NON_EVIDENCE_RE.search(h)]
    return bool(hits), len(hits), hits


def count_ligatures(text: str) -> int:
    return len(LIGATURE_RE.findall(text))


def count_hyphenation(text: str) -> tuple[int, int]:
    """(satir sonunda kalan tire, satir ici kalan tire) dondurur.

    Ikisini AYIRMAK sart. pdf-inspector satirlari birlestirirken tireyi
    SILMIYOR, sadece newline'i bosluga ceviriyor:
        pypdf      : "Üniversi-\\ntede"   -> satir sonu deseni
        inspector  : "Üniversi- tede"     -> satir ici deseni
    Tek sayac kullanilirsa inspector "0 hata" gibi gorunur -- yaniltici.
    Kelime her iki durumda da boluk; toplam ikisinin toplamidir.
    """
    return (len(HYPHEN_NEWLINE_RE.findall(text)),
            len(HYPHEN_INLINE_RE.findall(text)))


def count_footnote_sticks(text: str) -> int:
    return len(FOOTNOTE_STICK_RE.findall(text))


def _normalize_furniture(line: str) -> str:
    """Sayfa mobilyasi karsilastirmasi icin satiri sadelestirir.

    Sayfa numaralari her sayfada degistigi icin rakamlar atilir; boylece
    "Journal of Clinical Oncology 2199" ve "... 2200" ayni sayilir.
    """
    s = re.sub(r"\d+", "", line)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def count_page_furniture(pages: list[str]) -> int:
    """Sayfa ustu/altinin gövde metnine karismasini sayar.

    Yontem: her sayfanin ilk ve son (bos olmayan) satirini al. Ayni satir
    3+ sayfada tekrar ediyorsa bu bir ust/alt bilgisidir -- gövdeye
    karismis demektir. Kac tane boyle satir slotu oldugunu dondurur.
    """
    if len(pages) < 3:
        return 0

    slots: list[str] = []
    for txt in pages:
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        if not lines:
            continue
        slots.append(_normalize_furniture(lines[0]))
        if len(lines) > 1:
            slots.append(_normalize_furniture(lines[-1]))

    freq = Counter(s for s in slots if len(s) > 8)   # cok kisa satirlari eleme
    return sum(n for s, n in freq.items() if n >= 3)


def count_empty_pages(pages: list[str]) -> int:
    return sum(1 for p in pages if not p.strip())


def turkish_stats(text: str) -> tuple[int, int]:
    tr = sum(1 for ch in text if ch in TURKISH_CHARS)
    return tr, len(MOJIBAKE_RE.findall(text))


def measure(prefix: str, text: str, pages: list[str]) -> dict:
    """Bir ciktinin tum kusur sayaclarini hesaplar."""
    kapi_var, kapi_sayi, kapi_basliklar = gate_check(text)
    heads = headings(text)
    tr, bozuk = turkish_stats(text)
    tire_satirsonu, tire_satirici = count_hyphenation(text)
    return {
        f"{prefix}_karakter": len(text),
        f"{prefix}_sayfa": len(pages),
        f"{prefix}_baslik": len(heads),
        f"{prefix}_baslik_benzersiz": len(set(heads)),
        f"{prefix}_kapi_var": kapi_var,
        f"{prefix}_kapi_sayi": kapi_sayi,
        f"{prefix}_kapi_basliklar": " | ".join(h.lstrip("# ") for h in kapi_basliklar),
        f"{prefix}_ligatur": count_ligatures(text),
        f"{prefix}_tireleme": tire_satirsonu + tire_satirici,
        f"{prefix}_tireleme_satirsonu": tire_satirsonu,
        f"{prefix}_tireleme_satirici": tire_satirici,
        f"{prefix}_dipnot_isareti": count_footnote_sticks(text),
        f"{prefix}_sayfa_mobilyasi": count_page_furniture(pages),
        f"{prefix}_bos_sayfa": count_empty_pages(pages),
        f"{prefix}_tr_karakter": tr,
        f"{prefix}_bozuk_kodlama": bozuk,
    }


# ======================================================================
#  PARSERLAR
# ======================================================================

class WarningGrabber(logging.Handler):
    """pypdf'in logger uzerinden verdigi uyarilari toplar.

    "Rotated text discovered. Output will be incomplete." uyarisi
    warnings modulunden degil logging'den geliyor -- icerik kaybinin
    kanitidir, ayri sutuna kaydedilir.
    """

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def run_pypdf(path: str, layout: bool) -> tuple[str, list[str], list[str]]:
    """Mevcut sistemin mantigi. layout=False ise acquisition.py:238 ile ayni.

    Doner: (birlesik metin, sayfa listesi, uyari listesi)
    """
    grabber = WarningGrabber()
    lg = logging.getLogger("pypdf")
    lg.addHandler(grabber)
    prev_level = lg.level
    lg.setLevel(logging.WARNING)
    try:
        with open(path, "rb") as f:
            data = f.read()
        reader = pypdf.PdfReader(io.BytesIO(data))
        if layout:
            pages = [p.extract_text(extraction_mode="layout") or ""
                     for p in reader.pages]
        else:
            pages = [p.extract_text() or "" for p in reader.pages]
    finally:
        lg.removeHandler(grabber)
        lg.setLevel(prev_level)

    # Sistemdeki sarmalayici birebir korunuyor: her sayfa "# Page N" ile
    # baslar. Bu yuzden pypdf'in baslik sayisi = sayfa sayisi olur.
    text = "\n\n".join(
        f"# Page {i}\n\n{pg}" for i, pg in enumerate(pages, start=1)
    )
    return text, pages, grabber.messages


def run_inspector(path: str):
    return pdf_inspector.process_pdf(path)


def run_opendataloader(path: str) -> tuple[str, list[str]]:
    """opendataloader-pdf ile Markdown uretir.

    Doner: (birlesik metin, sayfa listesi)

    Iki tasarim notu -- raporda belirtilmeli:

    1. Bu kutuphane bir Java CLI'yi ALT SUREC olarak calistiriyor. Yani her
       cagride JVM bastan aciliyor (~0.5-0.8 sn sabit maliyet). Olculen sure
       bu maliyeti ICERIR. pypdf/inspector ayni surecte calistigi icin hiz
       karsilastirmasi bu yonuyle opendataloader aleyhine egiktir.

    2. include_header_footer VARSAYILAN OLARAK False. Yani kutuphane sayfa
       ust/alt bilgisini BILEREK atiyor. turkce_makale'de bu 450 karakter
       fark ediyor. Dolayisiyla 'sayfa mobilyasi' sayacinda opendataloader'in
       iyi cikmasi bir tasarim tercihidir, tesadufi bir ustunluk degildir.
       Karsilastirma varsayilan ayarla yapiliyor -- kullanicinin karsilasacagi
       davranis bu.

    3. image_output="off"  <-- VARSAYILANDAN SAPMA, gerekcesi:
       Varsayilan "external" her gomulu gorsel nesnesi icin markdown'a bir
       ![](...) satiri ekler. vgg'de bu 698 referans demek -- cunku o PDF
       (dvips/Ghostscript) sekilleri 737 kucuk SATIR ICI bitmap seride
       bolmus. Sonuc:

           external : 90.486 karakter, 1.828 satir
           off      :  54.292 karakter,   432 satir

       Yani ciktinin %40'i gorsel referansi. pypdf ve pdf-inspector hicbir
       gorsel referansi uretmedigi icin, varsayilanla olcmek METIN
       karsilastirmasini bozar (vgg'de odl pypdf'in %164'u gorunuyordu).
       Bu karsilastirma METIN cikarma kalitesini olctugunden gorseller
       kapatiliyor. Gorsel yetenegi AYRI olarak raporlanmalidir --
       html_uret.py gorselleri ACIK tutar, cunku orada amac gormek.
    """
    with tempfile.TemporaryDirectory(prefix="odl_") as tmp:
        opendataloader_pdf.convert(
            input_path=path,
            output_dir=tmp,
            format=["markdown"],
            markdown_page_separator=ODL_SEP,
            image_output="off",
            quiet=True,
        )
        md = ""
        for root, _dirs, files in os.walk(tmp):
            for fn in files:
                if fn.lower().endswith(".md"):
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        md = f.read()

    # Ayrac her sayfanin BASINA konuyor -> ilk parca daima bos, atiliyor.
    parts = md.split(ODL_SEP)
    pages = [p for p in parts[1:]] if len(parts) > 1 else ([md] if md else [])
    text = md.replace(ODL_SEP, "")
    return text, pages


def run_pymupdf4llm(path: str) -> tuple[str, list[str]]:
    """pymupdf4llm ile Markdown uretir. Doner: (birlesik metin, sayfa listesi).

    Neden bu aday onemli
    --------------------
    PyMuPDF platformda ZATEN bagimli (figure_analysis.py kullaniyor). Yani
    bu secenek YENI BIR SISTEM BAGIMLILIGI GETIRMIYOR -- opendataloader'in
    Java 11+ gereksinimi gibi bir engeli yok.

    Adi yaniltici: "4LLM" = "LLM ICIN", kendisi LLM CALISTIRMIYOR. PyMuPDF
    uzerine kurulu bir sarmalayici; tablo ve metni dogru sirayla birlestirip
    Markdown uretiyor.

    Surum notu: 1.28.2 ile birlikte `pymupdf_layout` (ONNX duzen modeli)
    geliyor. Resmi opendataloader-bench siralamasinda pymupdf4llm BASLIKTA
    0.412 almis; bizim olcumlerimizde en iyi baslik bulucu cikiyor. Bu fark
    buyuk olasilikla surum farkidir -- siralamadaki surum ONNX duzen modeli
    oncesine ait olabilir. Raporda bu belirtilmeli.

    Bedeli HIZ: belge basina 6-13 sn (inspector ~0.09 sn). Duzen modeli
    calistigi icin. Alim (ingestion) hattinda kabul edilebilir mi, urun
    tarafinin karari.
    """
    # page_chunks=True -> sayfa sayfa sozluk listesi
    parcalar = pymupdf4llm.to_markdown(path, page_chunks=True, show_progress=False)
    pages = [(p.get("text") or "") for p in parcalar]
    return "\n\n".join(pages), pages


def median_time(fn, runs: int) -> tuple[float, object]:
    """fn'i runs kere calistirir, ilk kosuyu atar, medyan sureyi dondurur."""
    times: list[float] = []
    result = None
    for i in range(runs):
        t0 = time.perf_counter()
        result = fn()
        dt = time.perf_counter() - t0
        if runs == 1 or i >= WARMUP:
            times.append(dt)
    return statistics.median(times), result


# ======================================================================
#  BASLIK ETIKETLEME DOSYASI
# ======================================================================

def write_heading_sheet(stem: str, text: str) -> int:
    """Elle 'gercek / uydurma' etiketlemek icin baslik listesi yazar.

    "142 baslik buldu" anlamsiz bir sayidir; "142 basligin kaci gercek bolum
    basligi" anlamlidir. O yuzden bu dosya elle doldurulmak uzere uretilir.
    """
    heads = headings(text)
    path = os.path.join(OUT_DIR, f"basliklar_{stem}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {stem} -- pdf-inspector'in buldugu basliklar\n")
        f.write("#\n")
        f.write("# 1. sutuna elle yaz:  G = gercek bolum basligi\n")
        f.write("#                      U = uydurma (sekil etiketi, cumle parcasi, ust bilgi)\n")
        f.write("#                      ? = emin degilim\n")
        f.write("#\n")
        f.write("# KAPI = evidence_quality kapisini tetikleyen baslik\n")
        f.write(f"# toplam: {len(heads)} baslik, {len(set(heads))} benzersiz\n")
        f.write("#\n")
        f.write("# etiket\tseviye\tkapi\tbaslik\n")
        f.write("# ------\t------\t----\t------\n")
        for h in heads:
            m = HEADING_RE.match(h)
            level = len(m.group(1)) if m else 0
            body = m.group(2) if m else h
            kapi = "KAPI" if NON_EVIDENCE_RE.search(h) else ""
            f.write(f"\t{level}\t{kapi}\t{body}\n")
    return len(heads)


# ======================================================================
#  ANA AKIS
# ======================================================================

def process_one(path: str, runs: int, do_layout: bool) -> dict:
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    size_mb = os.path.getsize(path) / 1e6
    row: dict = {"dosya": stem, "boyut_mb": round(size_mb, 2)}

    print(f"\n=== {name}  ({size_mb:.1f} MB) ===")

    # ---------- 1) pypdf plain  (sistemde su an kullanilan) ----------
    try:
        t, (text, pages, warns) = median_time(
            lambda: run_pypdf(path, layout=False), runs)
        row["pypdf_plain_sure_sn"] = round(t, 3)
        row.update(measure("pypdf_plain", text, pages))
        with open(os.path.join(OUT_DIR, f"{stem}__pypdf_plain.md"), "w",
                  encoding="utf-8") as f:
            f.write(text)
        print(f"  pypdf_plain   : {t:7.3f} sn  {len(text):8,} krk")
    except Exception:
        row["pypdf_plain_hata"] = traceback.format_exc(limit=1).strip()
        print(f"  pypdf_plain   : HATA")

    # ---------- 2) pypdf layout  (adil baseline) ----------
    if do_layout:
        try:
            t, (text, pages, warns) = median_time(
                lambda: run_pypdf(path, layout=True), runs)
            row["pypdf_layout_sure_sn"] = round(t, 3)
            row.update(measure("pypdf_layout", text, pages))
            uniq_warns = sorted(set(warns))
            row["pypdf_layout_uyari"] = len(warns)
            row["pypdf_layout_uyari_metin"] = " | ".join(uniq_warns)[:200]
            with open(os.path.join(OUT_DIR, f"{stem}__pypdf_layout.md"), "w",
                      encoding="utf-8") as f:
                f.write(text)
            uyari_not = f"  UYARI x{len(warns)}" if warns else ""
            print(f"  pypdf_layout  : {t:7.3f} sn  {len(text):8,} krk{uyari_not}")
            for w in uniq_warns:
                print(f"      ! {w}")
        except Exception:
            row["pypdf_layout_hata"] = traceback.format_exc(limit=1).strip()
            print(f"  pypdf_layout  : HATA")

    # ---------- 3) pdf-inspector ----------
    try:
        t, res = median_time(lambda: run_inspector(path), runs)
        md = res.markdown or ""

        # sayfa bazli metin (bos sayfa / sayfa mobilyasi hesabi icin).
        # Bu cagri sureye DAHIL DEGIL, sadece olcum verisi topluyor.
        try:
            pr = pdf_inspector.extract_pages_markdown(path)
            insp_pages = [p.markdown or "" for p in pr.pages]
        except Exception:
            insp_pages = []

        row["inspector_sure_sn"] = round(t, 3)
        row.update(measure("inspector", md, insp_pages))

        # --- saticinin kendi rapor ettigi degerler ---
        row.update({
            "insp_pdf_type": res.pdf_type,
            "insp_confidence": round(float(res.confidence), 3),
            "insp_sayfa_sayisi": res.page_count,
            "insp_kodlama_sorunu": res.has_encoding_issues,
            "insp_karmasik_duzen": res.is_complex_layout,
            "insp_sutunlu_sayfa": len(res.pages_with_columns or []),
            "insp_tablolu_sayfa": len(res.pages_with_tables or []),
            "insp_ocr_gereken_sayfa": len(res.pages_needing_ocr or []),
            "insp_kendi_sure_ms": res.processing_time_ms,
        })

        with open(os.path.join(OUT_DIR, f"{stem}__inspector.md"), "w",
                  encoding="utf-8") as f:
            f.write(md)
        n_heads = write_heading_sheet(stem, md)

        print(f"  inspector     : {t:7.3f} sn  {len(md):8,} krk")
        print(f"      tur={res.pdf_type} guven={res.confidence:.2f} "
              f"sayfa={res.page_count} sutunlu={len(res.pages_with_columns or [])} "
              f"tablolu={len(res.pages_with_tables or [])} "
              f"ocr={len(res.pages_needing_ocr or [])}")
        print(f"      basliklar -> out/basliklar_{stem}.txt ({n_heads} adet, "
              f"elle etiketlenecek)")
    except Exception:
        row["inspector_hata"] = traceback.format_exc(limit=1).strip()
        print(f"  inspector     : HATA")

    # ---------- 4) opendataloader ----------
    try:
        t, (text, pages) = median_time(lambda: run_opendataloader(path), runs)
        row["opendataloader_sure_sn"] = round(t, 3)
        row.update(measure("opendataloader", text, pages))
        with open(os.path.join(OUT_DIR, f"{stem}__opendataloader.md"), "w",
                  encoding="utf-8") as f:
            f.write(text)
        print(f"  opendataloader: {t:7.3f} sn  {len(text):8,} krk  "
              f"(JVM acilis maliyeti dahil)")
    except Exception:
        row["opendataloader_hata"] = traceback.format_exc(limit=1).strip()
        print(f"  opendataloader: HATA")

    # ---------- 5) pymupdf4llm ----------
    try:
        t, (text, pages) = median_time(lambda: run_pymupdf4llm(path), runs)
        row["pymupdf4llm_sure_sn"] = round(t, 3)
        row.update(measure("pymupdf4llm", text, pages))
        with open(os.path.join(OUT_DIR, f"{stem}__pymupdf4llm.md"), "w",
                  encoding="utf-8") as f:
            f.write(text)
        print(f"  pymupdf4llm   : {t:7.3f} sn  {len(text):8,} krk  "
              f"(ONNX duzen modeli dahil)")
    except Exception:
        row["pymupdf4llm_hata"] = traceback.format_exc(limit=1).strip()
        print(f"  pymupdf4llm   : HATA")

    # ---------- kusur karsilastirmasi ----------
    print("      kusur       ", end="")
    for label, key in (("ligatur", "ligatur"), ("tireleme", "tireleme"),
                       ("mobilya", "sayfa_mobilyasi"), ("bos_syf", "bos_sayfa")):
        vals = "/".join(str(row.get(f"{p}_{key}", "-")) for p in PARSERS)
        print(f" {label}={vals}", end="")
    print("   (plain/layout/insp/odl/p4llm)")

    return row


def main() -> None:
    quick = "--quick" in sys.argv
    do_layout = "--no-layout" not in sys.argv
    runs = 1 if quick else RUNS

    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].lower()

    os.makedirs(OUT_DIR, exist_ok=True)

    # Sadece corpus/ altindaki dosyalar islenir. Kok klasordeki PDF'ler
    # bilerek disarida birakildi -- ayni dosya iki kez islenmesin diye.
    pdfs = sorted(
        os.path.join(CORPUS_DIR, n)
        for n in os.listdir(CORPUS_DIR)
        if n.lower().endswith(".pdf")
    )
    if only:
        pdfs = [p for p in pdfs if only in os.path.basename(p).lower()]
    if not pdfs:
        print(f"corpus/ altinda PDF yok: {CORPUS_DIR}")
        return

    mod = "tek kosu" if quick else f"{runs} kosu, ilki atiliyor, medyan"
    print(f"{len(pdfs)} dosya | {mod} | layout modu: "
          f"{'acik' if do_layout else 'KAPALI'}")

    rows = [process_one(p, runs, do_layout) for p in pdfs]

    # ---------------- CSV ----------------
    columns: list[str] = []
    for r in rows:
        for k in r:
            if k not in columns:
                columns.append(k)
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)

    # ---------------- ozet: hiz ----------------
    print("\n" + "=" * 104)
    print("HIZ  (medyan saniye)")
    print("=" * 104)
    print(f"{'dosya':30} {'tur':12} {'syf':>4} {'plain':>9} {'layout':>9} "
          f"{'inspector':>10} {'odl':>9} {'p4llm':>9} {'uyari':>6}")
    print("-" * 116)
    for r in rows:
        print(f"{r['dosya'][:30]:30} "
              f"{str(r.get('insp_pdf_type', '?'))[:12]:12} "
              f"{str(r.get('insp_sayfa_sayisi', '?')):>4} "
              f"{r.get('pypdf_plain_sure_sn', '-'):>9} "
              f"{r.get('pypdf_layout_sure_sn', '-'):>9} "
              f"{r.get('inspector_sure_sn', '-'):>10} "
              f"{r.get('opendataloader_sure_sn', '-'):>9} "
              f"{r.get('pymupdf4llm_sure_sn', '-'):>9} "
              f"{r.get('pypdf_layout_uyari', '-'):>6}")
    print("\nNot: odl sutunu JVM acilis maliyetini (~0.5-0.8 sn) icerir; digerleri")
    print("     ayni Python surecinde calisir. Hiz kiyasi bu yonuyle esit degildir.")

    # ---------------- ozet: kusurlar ----------------
    print("\n" + "=" * 104)
    print("KUSUR  (plain / layout / insp / odl / p4llm -- dusuk olan iyi)")
    print("=" * 116)
    print(f"{'dosya':28} {'ligatur':>22} {'tireleme':>22} "
          f"{'mobilya':>18} {'kapi':>14}")
    print("-" * 104)
    for r in rows:
        def trio(key: str) -> str:
            return "/".join(str(r.get(f"{p}_{key}", "-")) for p in PARSERS)

        kapi = "/".join(
            "E" if r.get(f"{p}_kapi_var") else "H" for p in PARSERS
        )
        print(f"{r['dosya'][:28]:28} {trio('ligatur'):>22} "
              f"{trio('tireleme'):>22} {trio('sayfa_mobilyasi'):>18} "
              f"{kapi:>14}")
    print("-" * 104)

    # ---------------- ozet: kapi ----------------
    n = len(rows)
    print("\nKAPI (evidence_quality.is_non_evidence_section tetiklenir mi?)")
    for p in PARSERS:
        hit = sum(1 for r in rows if r.get(f"{p}_kapi_var"))
        print(f"  {p:14}: {hit}/{n} dosyada tetikleniyor")

    print(f"\nCSV        : {CSV_PATH}")
    print(f"Ciktilar   : {OUT_DIR}")
    print(f"Baslik listeleri: out/basliklar_*.txt  <- elle G/U etiketle")


if __name__ == "__main__":
    main()
