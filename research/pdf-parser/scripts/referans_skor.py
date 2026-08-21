"""arXiv HTML'ini REFERANS alarak parser'lari puanlar.

NEDEN BU MUMKUN
---------------
arXiv HTML'i LaTeXML ile, makalenin LATEX KAYNAGINDAN uretiliyor -- PDF'ten
degil. Yani bolum basliklari, tablo yapisi ve okuma sirasi kaynakta zaten
isaretli. Bu, PDF'ten turetilmis herhangi bir referanstan cok daha guvenilir
bir kiyas noktasi verir.

NE KADAR GUVENILIR -- DURUSTCE
------------------------------
1. Elle etiketlenmis bir "ground truth" DEGIL, makine donusumu. Kaynagi
   otoriter oldugu icin YAPI (baslik, bolum) guvenilir; ama LaTeXML bir PDF
   parser'inin uretmesi BEKLENMEYECEK seyler de uretir (float yerlesimi,
   sekil sirasi). Bu yuzden:
       - baslik skoru (MHS)  -> anlamli
       - metin skoru (NID)   -> daha gurultulu, mutlak deger degil parserlar
                                ARASI SIRALAMA icin okunmali
2. Korpusun 9 belgesinden 6'si arXiv'de. Referansi OLMAYAN ikisi
   (sybil, turkce) tam da korpusun EN ZOR ikisi. Yani bu skorlar
   korpusun KOLAY tarafini olcuyor ve gercekte olduklarindan IYIMSER.
   Raporda bu mutlaka yazilmali.
3. Bu, opendataloader-bench'in NID/TEDS/MHS kodunun BIREBIR AYNISI DEGIL.
   Ayni FIKRIN burada tanimlanmis karsiligi. Skorlar onlarin yayinladigi
   sayilarla dogrudan kiyaslanmamalidir.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\referans_skor.py --indir   # HTML'leri indir
    .\\.venv\\Scripts\\python.exe src\\referans_skor.py           # skorla

Cikti
-----
    referans/<belge>.html      indirilen arXiv HTML'i
    referans_skorlar.csv       parser x belge skor tablosu
"""
from __future__ import annotations

import csv
import os
import re
import sys
import unicodedata

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
OUT_DIR = os.path.join(BASE, "out")
REF_DIR = os.path.join(BASE, "referans")
CSV_PATH = os.path.join(BASE, "referans_skorlar.csv")

from apted import APTED, Config  # noqa: E402
from apted.helpers import Tree  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402
from rapidfuzz.distance import Indel  # noqa: E402

# PDF'lerimizin arXiv kimlikleri ve SURUMLERI.
# Surum onemli: /html/1810.04805 en son surumu verir; bizim PDF v2 ise
# farkli metni kiyaslamis oluruz. Surum PDF'in kenar damgasindan alindi.
ARXIV = {
    "vgg_tablo_agirlikli": "1409.1556v6",
    "resnet_2sutun_gorsel": "1512.03385v1",
    "attention_tablo": "1706.03762v5",
    "bert_2sutun_dipnot": "1810.04805v2",
    "gpt3_uzun_75sayfa": "2005.14165v4",
    "gpt4_uzun_gorsel": "2303.08774v3",
}

PARSERS = ["pypdf_plain", "inspector", "opendataloader", "pymupdf4llm"]


# ======================================================================
#  INDIRME
# ======================================================================

def indir() -> None:
    import urllib.request

    os.makedirs(REF_DIR, exist_ok=True)
    for stem, aid in ARXIV.items():
        hedef = os.path.join(REF_DIR, f"{stem}.html")
        if os.path.exists(hedef):
            print(f"  atlandi (var): {stem}")
            continue
        for url in (f"https://arxiv.org/html/{aid}",
                    f"https://arxiv.org/html/{aid.split('v')[0]}"):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "staj-parser-degerlendirme/1.0"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    veri = r.read()
                with open(hedef, "wb") as f:
                    f.write(veri)
                print(f"  indi: {stem:24} {len(veri):>9,} bayt  <- {url}")
                break
            except Exception as e:
                print(f"  HATA {stem} {url}: {type(e).__name__}")


# ======================================================================
#  NORMALIZASYON
# ======================================================================

# Olcutumuz: "sadece daha cirkin gorunmek hata degil (bos satir, girinti)".
# Bu yuzden BOSLUK normalize edilir. Ligatur ve tireleme normalize EDILMEZ --
# onlar gercek kusur ve puanda gorunmeleri gerekir.

def temiz(s: str, agresif: bool = False) -> str:
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    if agresif:                      # yalnizca BASLIK eslestirmede
        s = re.sub(r"[\uFB00-\uFB04]",
                   lambda m: {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
                              "\ufb03": "ffi", "\ufb04": "ffl"}[m.group()], s)
        s = re.sub(r"[^\w\s]", "", s)
        s = re.sub(r"\s+", " ", s).strip()
    return s


def markdown_sadelestir(md: str) -> str:
    """Markdown isaretlerini atar -- kiyas METIN uzerinden olsun."""
    md = re.sub(r"^\s*\|.*$", " ", md, flags=re.M)      # tablo satirlari
    md = re.sub(r"^#{1,6}\s*", "", md, flags=re.M)      # baslik isareti
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", md)       # gorsel
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)    # baglanti
    md = re.sub(r"[*_`>#]", "", md)
    md = re.sub(r"<[^>]+>", " ", md)                    # <u> vb.
    return temiz(md)


# ======================================================================
#  REFERANSTAN CIKARIM
# ======================================================================

ATLA_BASLIK = re.compile(r"^(abstract|references|bibliography|acknowledge?ments?)$")


def referans_oku(path: str) -> tuple[str, list[str], list]:
    with open(path, encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    for etiket in soup(["script", "style", "nav", "footer"]):
        etiket.decompose()

    basliklar = []
    for h in soup.find_all(re.compile(r"^h[1-6]$")):
        t = temiz(h.get_text(" "), agresif=True)
        # LaTeXML basliga numarayi ayri span olarak koyar: "1 Introduction"
        t = re.sub(r"^\d+(\.\d+)*\s+", "", t)
        if t and len(t) < 120:
            basliklar.append(t)

    tablolar = html_tablolari(soup)
    return temiz(soup.get_text(" ")), basliklar, tablolar


# ======================================================================
#  SKORLAR
# ======================================================================

def nid(aday: str, referans: str) -> float:
    """Normalize Indel benzerligi [0,1]. 1 = birebir ayni.

    opendataloader-bench'in NID metrigi ile AYNI FIKIR, ayni kod DEGIL.
    Cok uzun metinlerde maliyetli oldugu icin ilk N karaktere bakilir.
    """
    N = 120_000
    return Indel.normalized_similarity(aday[:N], referans[:N])


# ----------------------------------------------------------------------
#  TEDS  (tablo yapisi)
# ----------------------------------------------------------------------
# opendataloader-bench'in TEDS'i ile AYNI FIKIR, ayni kod DEGIL:
# tabloyu bir agaca cevirip (table > tr > td) iki agac arasindaki
# duzenleme mesafesini olcer. Skor = 1 - mesafe / max(dugum sayisi).
#
# Bizim olcutumuzun 4. maddesi ("bir sayinin hangi satir/sutuna ait oldugu
# belli olmali") tam olarak bunu sorar: hucre icerigi dogru hucrede mi.
#
# SINIRLAR -- raporda yazilmali:
#   * Aday ile referans tablolarini ESLESTIRMEK gerekiyor; parser'lar farkli
#     sayida tablo uretiyor. Hucre metni ortakligina gore en iyi eslesme
#     seciliyor. Yanlis eslesme skoru dusurur.
#   * Referansta olup adayda hic karsiligi olmayan tablo 0 sayilir.
#   * Cok buyuk tablolar TEDS_TAVAN hucreye kirpiliyor (APTED maliyetli).

TEDS_TAVAN = 400        # tablo basina azami hucre
TEDS_MAX_TABLO = 25     # belge basina azami tablo (maliyet siniri)


class _TedsConfig(Config):
    """Etiket degistirme maliyeti: hucre metinlerinin benzemezligi."""

    def rename(self, n1, n2):
        t1, t2 = n1.name, n2.name
        tip1, tip2 = t1.split("\x00", 1)[0], t2.split("\x00", 1)[0]
        if tip1 != tip2:
            return 1.0
        if tip1 != "td":
            return 0.0
        a = t1.split("\x00", 1)[1] if "\x00" in t1 else ""
        b = t2.split("\x00", 1)[1] if "\x00" in t2 else ""
        if not a and not b:
            return 0.0
        return 1.0 - Indel.normalized_similarity(a, b)


def _agac(izgara: list[list[str]]) -> tuple[Tree, int]:
    satirlar, n = [], 1
    for satir in izgara:
        hucreler = [Tree(f"td\x00{h}") for h in satir]
        n += 1 + len(hucreler)
        satirlar.append(Tree("tr\x00", *hucreler))
    return Tree("table\x00", *satirlar), n


def _kirp(izgara: list[list[str]]) -> list[list[str]]:
    kirpik, sayac = [], 0
    for satir in izgara:
        if sayac >= TEDS_TAVAN:
            break
        kirpik.append(satir[:40])
        sayac += len(satir[:40])
    return kirpik


def _izgara_metni(izgara: list[list[str]]) -> set:
    return {h for satir in izgara for h in satir if h}


def html_tablolari(soup) -> list[list[list[str]]]:
    """Referanstaki GERCEK veri tablolari.

    ONEMLI: LaTeXML denklemleri de <table> olarak yazar
    (class="ltx_equation ltx_eqn_table"). Bunlar veri tablosu DEGIL, matematik
    formulu. Elenmezlerse parser'lar "formulu tablo yapmadiklari icin"
    cezalandirilir -- attention'da 9 tablonun 4'u boyleydi.
    Yalnizca ltx_tabular (gercek tablo ortami) tutulur.
    """
    tablolar = []
    for t in soup.find_all("table"):
        sinif = " ".join(t.get("class") or [])
        if "ltx_eqn" in sinif or "ltx_equation" in sinif:
            continue                       # denklem, tablo degil
        izgara = []
        for tr in t.find_all("tr"):
            hucreler = [temiz(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
            if hucreler:
                izgara.append(hucreler)
        if len(izgara) >= 2:
            tablolar.append(_kirp(izgara))
    return tablolar[:TEDS_MAX_TABLO]


def md_tablolari(md: str) -> list[list[list[str]]]:
    tablolar, blok = [], []
    for satir in md.splitlines():
        s = satir.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 2:
            hucreler = [temiz(c) for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in hucreler if c):
                continue                      # ---|--- ayirici
            blok.append(hucreler)
        else:
            if len(blok) >= 2:
                tablolar.append(_kirp(blok))
            blok = []
    if len(blok) >= 2:
        tablolar.append(_kirp(blok))
    return tablolar[:TEDS_MAX_TABLO]


def teds(aday_tablolar, ref_tablolar) -> float:
    """Referanstaki her tablo icin en iyi eslesen adayla TEDS, ortalamasi."""
    if not ref_tablolar:
        return float("nan")            # tablosuz belge -> ortalamaya katilmaz
    if not aday_tablolar:
        return 0.0

    skorlar = []
    kullanildi = set()
    for ref in ref_tablolar:
        ref_kume = _izgara_metni(ref)
        # icerik ortakligina gore en iyi aday
        en_iyi, en_iyi_i = -1.0, None
        for i, ad in enumerate(aday_tablolar):
            if i in kullanildi:
                continue
            ort = len(ref_kume & _izgara_metni(ad))
            skor = ort / max(1, len(ref_kume))
            if skor > en_iyi:
                en_iyi, en_iyi_i = skor, i
        if en_iyi_i is None or en_iyi <= 0:
            skorlar.append(0.0)
            continue
        kullanildi.add(en_iyi_i)

        t1, n1 = _agac(ref)
        t2, n2 = _agac(aday_tablolar[en_iyi_i])
        try:
            mesafe = APTED(t1, t2, _TedsConfig()).compute_edit_distance()
            skorlar.append(max(0.0, 1.0 - mesafe / max(n1, n2)))
        except Exception:
            skorlar.append(0.0)

    return sum(skorlar) / len(skorlar)


def baslik_skoru(aday_md: str, ref_basliklar: list[str]) -> dict:
    """Baslik bulma basarisi.

    Iki sayi uretilir:
      * MHS-benzeri : baslik DIZISININ referansa benzerligi (onlarin fikri)
      * kesinlik/duyarlilik/F1 : bizim raporumuzun dilinde --
            kesinlik  = uretilen basliklarin kaci GERCEK  (uydurma basligin tersi)
            duyarlilik= gercek basliklarin kaci BULUNDU   (kacirilan basligin tersi)
    """
    aday = []
    for satir in aday_md.splitlines():
        m = re.match(r"^#{1,6}\s+(\S.*)$", satir)
        if m:
            t = temiz(m.group(1), agresif=True)
            t = re.sub(r"^\d+(\.\d+)*\s+", "", t)
            t = re.sub(r"^page \d+$", "", t)     # pypdf'in "# Page N" sarmalayicisi
            if t:
                aday.append(t)

    ref_kume = set(ref_basliklar)
    aday_kume = set(aday)
    if not ref_kume:
        return {"mhs": 0.0, "kesinlik": 0.0, "duyarlilik": 0.0, "f1": 0.0,
                "aday_baslik": len(aday), "ref_baslik": 0}

    # esik-esli eslestirme: birebir olmayan ama cok benzer basliklari da say
    def eslesir(a: str, kume: set) -> bool:
        if a in kume:
            return True
        return any(Indel.normalized_similarity(a, b) > 0.85 for b in kume)

    dogru_aday = sum(1 for a in aday_kume if eslesir(a, ref_kume))
    bulunan_ref = sum(1 for r in ref_kume if eslesir(r, aday_kume))

    kesinlik = dogru_aday / len(aday_kume) if aday_kume else 0.0
    duyarlilik = bulunan_ref / len(ref_kume)
    f1 = (2 * kesinlik * duyarlilik / (kesinlik + duyarlilik)
          if (kesinlik + duyarlilik) else 0.0)
    mhs = Indel.normalized_similarity(" | ".join(aday), " | ".join(ref_basliklar))

    return {"mhs": round(mhs, 4), "kesinlik": round(kesinlik, 4),
            "duyarlilik": round(duyarlilik, 4), "f1": round(f1, 4),
            "aday_baslik": len(aday), "ref_baslik": len(ref_kume)}


# ======================================================================
#  ANA AKIS
# ======================================================================

def main() -> None:
    if "--indir" in sys.argv:
        print("arXiv HTML referanslari indiriliyor...")
        indir()
        return

    if not os.path.isdir(REF_DIR):
        print("referans/ yok. Once:  python src\\referans_skor.py --indir")
        return

    satirlar = []
    for stem in ARXIV:
        ref_path = os.path.join(REF_DIR, f"{stem}.html")
        if not os.path.exists(ref_path):
            print(f"  ATLANDI (referans yok): {stem}")
            continue

        ref_metin, ref_basliklar, ref_tablolar = referans_oku(ref_path)
        print(f"\n=== {stem} ===")
        print(f"  referans: {len(ref_metin):,} krk, "
              f"{len(set(ref_basliklar))} benzersiz baslik, "
              f"{len(ref_tablolar)} tablo")

        for p in PARSERS:
            md_path = os.path.join(OUT_DIR, f"{stem}__{p}.md")
            if not os.path.exists(md_path):
                print(f"    {p:16} cikti yok, atlandi")
                continue
            with open(md_path, encoding="utf-8") as f:
                md = f.read()

            n = nid(markdown_sadelestir(md), ref_metin)
            b = baslik_skoru(md, ref_basliklar)
            aday_tablolar = md_tablolari(md)
            t = teds(aday_tablolar, ref_tablolar)

            # Overall: onlarin yaptigi gibi uc metrigin ortalamasi.
            # NaN olan metrik (tablosuz belge) ortalamaya KATILMAZ.
            gecerli = [x for x in (n, t, b["mhs"]) if x == x]
            genel = sum(gecerli) / len(gecerli) if gecerli else 0.0

            satirlar.append({
                "dosya": stem, "parser": p,
                "genel": round(genel, 4), "nid": round(n, 4),
                "teds": ("" if t != t else round(t, 4)),
                "aday_tablo": len(aday_tablolar), "ref_tablo": len(ref_tablolar),
                **b})
            t_str = "  —  " if t != t else f"{t:.3f}"
            print(f"    {p:16} GENEL={genel:.3f}  NID={n:.3f}  TEDS={t_str}  "
                  f"MHS={b['mhs']:.3f}  F1={b['f1']:.3f}  "
                  f"tablo {len(aday_tablolar)} vs ref {len(ref_tablolar)}")

    if not satirlar:
        return
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(satirlar[0]))
        w.writeheader()
        w.writerows(satirlar)

    # ---- parser ortalamalari (opendataloader-bench siralamasi bicimi) ----
    print("\n" + "=" * 86)
    print("SIRALAMA  (6 arXiv belgesi -- korpusun KOLAY tarafi, iyimser)")
    print("opendataloader-bench'in sutun duzeni; ayni FIKIR, ayni kod DEGIL")
    print("=" * 86)
    print(f"{'ENGINE':18}{'OVERALL':>10}{'READING ORDER':>15}{'TABLES':>9}"
          f"{'HEADINGS':>11}{'baslik F1':>11}")
    print("-" * 86)
    ozet = []
    for p in PARSERS:
        alt = [s for s in satirlar if s["parser"] == p]
        if not alt:
            continue

        def ort(k):
            d = [s[k] for s in alt if s[k] != "" and s[k] == s[k]]
            return sum(d) / len(d) if d else 0.0

        ozet.append((p, ort("genel"), ort("nid"), ort("teds"), ort("mhs"),
                     ort("f1")))
    for p, g, n, t, m, f1 in sorted(ozet, key=lambda x: -x[1]):
        print(f"{p:18}{g:>10.3f}{n:>15.3f}{t:>9.3f}{m:>11.3f}{f1:>11.3f}")
    print("-" * 86)
    print(f"\nCSV: {CSV_PATH}")
    print("\nUYARI: sybil ve turkce (korpusun en zor ikisi) arXiv'de olmadigi")
    print("       icin bu tabloda YOK. Skorlar gercekten daha iyimserdir.")


if __name__ == "__main__":
    main()
