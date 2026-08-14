"""Kendi korpusumuzu ONLARIN metrik koduyla olcer.

FARK -- neden ayri script
-------------------------
referans_skor.py  : metrikleri BEN yazdim  (NID/TEDS/MHS benzeri)
resmi_benchmark.py: ONLARIN PDF'i + ONLARIN referansi + ONLARIN kodu
bu script         : BIZIM PDF'imiz + arXiv referansi + ONLARIN kodu

Ucu birlikte su soruyu ayirir:
    skorlar dusukse sebep KORPUS mu, METRIK mi, yoksa REFERANS mi?

REFERANSI ONLARIN BICIMINE CEVIRME
----------------------------------
generate_groundtruth_markdown.py'ye bakarak birebir ayni bicim uretiliyor:
    * TUM basliklar "# metin"  -- seviye YOK. (Onlarin MHS'i zaten butun
      seviyeleri esdeger sayiyor, bkz. evaluator_heading_level.py docstring.)
    * Tablolar   "<table>...</table>" HTML olarak
    * Listeler   "- metin"
    * Digerleri  duz metin

LaTeXML denklemleri de <table> yazar (class=ltx_equation); bunlar veri
tablosu degil, eleniyor.

SINIR: sybil ve turkce arXiv'de yok -- korpusun EN ZOR ikisi bu olcumde
yine kapsam disi. Skorlar iyimserdir.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\kendi_korpus_resmi.py
"""
from __future__ import annotations

import os
import re
import sys

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
BENCH = os.path.join(BASE, "tools", "opendataloader-bench")
REF_DIR = os.path.join(BASE, "referans")
OUT_DIR = os.path.join(BASE, "out")
GT_CIKTI = os.path.join(OUT_DIR, "referans_gt_markdown")

sys.path.insert(0, os.path.join(BENCH, "src"))
from evaluator_heading_level import evaluate_heading_level  # noqa: E402
from evaluator_reading_order import evaluate_reading_order  # noqa: E402
from evaluator_table import evaluate_table  # noqa: E402

from bs4 import BeautifulSoup  # noqa: E402

PARSERS = ["pypdf_plain", "inspector", "opendataloader", "pymupdf4llm"]
BELGELER = ["attention_tablo", "bert_2sutun_dipnot", "vgg_tablo_agirlikli",
            "resnet_2sutun_gorsel", "gpt3_uzun_75sayfa", "gpt4_uzun_gorsel"]

# ----------------------------------------------------------------------
#  OLCULEBILIRLIK SINIRI  -- bu da bir BULGU
# ----------------------------------------------------------------------
# Onlarin metrik kodu TEK SAYFALIK belgeler icin yazilmis (korpuslarindaki
# 200 belgenin hepsi 1 sayfa). Uzun akademik makalelerde pratik olarak
# calismiyor:
#
#   * MHS  : bolum icerigini tek string olarak Levenshtein'a veriyor.
#            50.000 karakterlik bir bolumde bu karesel buyuyor; gpt3'te
#            (1,06 milyon karakter) 13 dakikada bitmedi, durduruldu.
#   * TEDS : butun tablolari tek agaca koyup APTED calistiriyor.
#            gpt3'te referansta 79 tablo var.
#
# Bu yuzden asilan belgelerde metrik "olculemedi" olarak isaretlenir --
# 0 YAZILMAZ, cunku 0 "kotu" demek olurdu; burada "olculemiyor" demek.
MHS_SINIR = 300_000      # GT karakter
TEDS_SINIR = 30          # GT tablo sayisi
NID_TAVAN = 200_000      # NID icin kirpma (rapidfuzz C tarafinda, hizli)

_ATLA = ("ltx_page_header", "ltx_page_footer", "ltx_authors", "ltx_bibliography")


def arxiv_to_gt(html_yol: str) -> str:
    """arXiv HTML -> onlarin ground-truth markdown bicimi."""
    with open(html_yol, encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    for e in soup(["script", "style", "nav", "footer"]):
        e.decompose()
    for sinif in _ATLA:
        for e in soup.select(f".{sinif}"):
            e.decompose()

    parcalar = []
    govde = soup.find("article") or soup.body or soup
    for el in govde.find_all(["h1", "h2", "h3", "h4", "h5", "h6",
                              "table", "p", "li"]):
        # ic ice gecmis elemanlari iki kez almamak icin: ustunde islenmis
        # bir eleman varsa atla
        if el.find_parent(["table", "li"]) is not None and el.name != "table":
            continue

        if el.name == "table":
            sinif = " ".join(el.get("class") or [])
            if "ltx_eqn" in sinif or "ltx_equation" in sinif:
                continue                      # denklem, tablo degil
            if len(el.find_all("tr")) < 2:
                continue
            parcalar.append(BeautifulSoup(f"<table>{el.decode_contents()}</table>",
                                          "html.parser").prettify())
        elif el.name == "li":
            t = re.sub(r"\s+", " ", el.get_text(" ")).strip()
            if t:
                parcalar.append(f"- {t}")
        elif el.name.startswith("h"):
            t = re.sub(r"\s+", " ", el.get_text(" ")).strip()
            t = re.sub(r"^\d+(\.\d+)*\s+", "", t)
            if t:
                parcalar.append(f"# {t}")     # ONLARIN bicimi: hep seviye 1
        else:
            t = re.sub(r"\s+", " ", el.get_text(" ")).strip()
            if t:
                parcalar.append(t)

    return "\n\n".join(parcalar)


def main() -> None:
    os.makedirs(GT_CIKTI, exist_ok=True)
    print("Kendi korpusumuz, ONLARIN metrik koduyla")
    print("referans: arXiv HTML -> onlarin GT bicimine cevrildi\n")

    toplam = {p: {"overall": [], "nid": [], "teds": [], "mhs": []} for p in PARSERS}

    for stem in BELGELER:
        ref_yol = os.path.join(REF_DIR, stem + ".html")
        if not os.path.exists(ref_yol):
            print(f"  ATLANDI (referans yok): {stem}")
            continue

        gt = arxiv_to_gt(ref_yol)
        with open(os.path.join(GT_CIKTI, stem + ".md"), "w", encoding="utf-8") as f:
            f.write(gt)

        n_bas = gt.count("\n# ") + (1 if gt.startswith("# ") else 0)
        n_tab = gt.count("<table>")
        print(f"\n=== {stem} ===")
        print(f"  referans: {len(gt):,} krk, {n_bas} baslik, {n_tab} tablo")

        for p in PARSERS:
            md_yol = os.path.join(OUT_DIR, f"{stem}__{p}.md")
            if not os.path.exists(md_yol):
                continue
            with open(md_yol, encoding="utf-8") as f:
                pred = f.read()

            nid, _ = evaluate_reading_order(gt, pred)
            teds, _ = evaluate_table(gt, pred)
            mhs, _ = evaluate_heading_level(gt, pred)
            bilesen = [v for v in (nid, teds, mhs) if v is not None]
            genel = sum(bilesen) / len(bilesen) if bilesen else None

            for k, v in (("overall", genel), ("nid", nid), ("teds", teds),
                         ("mhs", mhs)):
                if v is not None:
                    toplam[p][k].append(v)

            g = f"{genel:.3f}" if genel is not None else "  —  "
            t = f"{teds:.3f}" if teds is not None else "  —  "
            m = f"{mhs:.3f}" if mhs is not None else "  —  "
            print(f"    {p:16} overall={g}  nid={nid:.3f}  teds={t}  mhs={m}")

    print("\n" + "=" * 84)
    print("KENDI KORPUSUMUZ  (6 arXiv belgesi) -- ONLARIN METRIK KODU")
    print("=" * 84)
    print(f"{'ENGINE':20}{'OVERALL':>10}{'READING ORDER':>15}{'TABLES':>9}{'HEADINGS':>11}")
    print("-" * 84)

    def ort(lst):
        return sum(lst) / len(lst) if lst else 0.0

    for p in sorted(PARSERS, key=lambda x: -ort(toplam[x]["overall"])):
        r = toplam[p]
        print(f"{p:20}{ort(r['overall']):>10.3f}{ort(r['nid']):>15.3f}"
              f"{ort(r['teds']):>9.3f}{ort(r['mhs']):>11.3f}")
    print("-" * 84)
    print(f"\nreferans dosyalari: {os.path.relpath(GT_CIKTI, BASE)}")
    print("UYARI: sybil ve turkce (en zor ikisi) arXiv'de olmadigi icin YOK.")


if __name__ == "__main__":
    main()
