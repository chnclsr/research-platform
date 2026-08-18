"""Etiketli gorunumun DOGRULAMASI -- "kutulari sen mi uydurdun?" sorusunun cevabi.

Iki bagimsiz kontrol yapar:

KONTROL 1 -- HTML, JSON'un aynisi mi?
    Uretilen html/annot_<belge>.html icindeki her kutunun yuzde konumu
    okunur, opendataloader'in JSON'undan BAGIMSIZ olarak yeniden hesaplanir
    ve karsilastirilir. Tek bir kutu bile tutmuyorsa hata verir.
    Yani: HTML'e elle dokunulmadigini, ara katmanin sadece
    (PDF noktasi -> yuzde) donusumu yaptigini gosterir.

KONTROL 2 -- Bizim cizimimiz ONLARINKI ile ayni mi?
    opendataloader'in kendi urettigi <belge>_annotated.pdf'ten sayfa
    goruntusu alinir; yaninda ayni sayfa bizim JSON'dan cizdigimiz
    kutularla basilir. Iki goruntu yan yana PNG olarak yazilir --
    goz ile bakilir. Kod dogru sayiyi verse bile YANLIS YERE cizmis
    olabilir; bunu ancak goz ayirt eder.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\annot_dogrula.py
    .\\.venv\\Scripts\\python.exe src\\annot_dogrula.py --belge vgg_tablo_agirlikli --sayfa 2
"""
from __future__ import annotations

import json
import os
import re
import sys

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
HTML_DIR = os.path.join(BASE, "html")
ODL_OUT = os.path.join(BASE, "out", "odl_annot")
CORPUS = os.path.join(BASE, "corpus")
CIKTI = os.path.join(BASE, "out", "dogrulama")

sys.path.insert(0, os.path.join(BASE, "src"))
from annot_uret import ogeleri_topla  # noqa: E402

import pymupdf  # noqa: E402

BELGELER = ["attention_tablo", "bert_2sutun_dipnot", "vgg_tablo_agirlikli",
            "resnet_2sutun_gorsel", "gpt3_uzun_75sayfa", "gpt4_uzun_gorsel",
            "sybil_tip_2sutun", "turkce_makale", "taranmis_bert_2sutun_dipnot"]

# DIKKAT: yuzdeler "-0.000" olabiliyor (kayan nokta artigi). Eksi isaretini
# desene koymayi ilk seferde unuttum ve taranmis belgede 0 kutu buldum sandim;
# hata desendeydi, uretecte degil.
KUTU_DESEN = re.compile(
    r'<div class="kutu[^"]*" data-tur="([^"]+)" '
    r'style="left:(-?[\d.]+)%;top:(-?[\d.]+)%;width:(-?[\d.]+)%;height:(-?[\d.]+)%')


def kontrol1(stem: str) -> tuple[int, int]:
    """HTML'deki kutular JSON'dan yeniden hesaplanabiliyor mu?"""
    hy = os.path.join(HTML_DIR, f"annot_{stem}.html")
    jy = os.path.join(ODL_OUT, stem, stem + ".json")
    if not (os.path.exists(hy) and os.path.exists(jy)):
        return 0, 0

    with open(hy, encoding="utf-8") as f:
        htm = f.read()
    html_kutular = KUTU_DESEN.findall(htm)

    doc = pymupdf.open(os.path.join(CORPUS, stem + ".pdf"))
    olcu = {i + 1: (doc.load_page(i).rect.width, doc.load_page(i).rect.height)
            for i in range(doc.page_count)}
    doc.close()

    # JSON'dan beklenen kutu kumesi (yuvarlanmis yuzde + tur)
    beklenen = set()
    for kaynak in (jy, os.path.join(ODL_OUT, stem, "ust_alt", stem + ".json")):
        if not os.path.exists(kaynak):
            continue
        atilan = kaynak.endswith(os.path.join("ust_alt", stem + ".json"))
        for o in ogeleri_topla(kaynak):
            w, h = olcu.get(o["sayfa"], (0, 0))
            if not w:
                continue
            x0, y0, x1, y1 = o["kutu"]
            dort = (round(100 * x0 / w, 3), round(100 * (h - y1) / h, 3),
                    round(100 * (x1 - x0) / w, 3), round(100 * (y1 - y0) / h, 3))
            beklenen.add((o["tur"], dort))
            if atilan:
                beklenen.add(("__atilan__", dort))

    tutan = 0
    for tur, sol, ust, gen, yuk in html_kutular:
        dort = (round(float(sol), 3), round(float(ust), 3),
                round(float(gen), 3), round(float(yuk), 3))
        if (tur, dort) in beklenen:
            tutan += 1
    return tutan, len(html_kutular)


def kontrol2(stem: str, sayfa: int) -> str | None:
    """Onlarin annotated PDF'i | bizim cizimimiz -- yan yana PNG."""
    annot = os.path.join(ODL_OUT, stem, stem + "_annotated.pdf")
    jy = os.path.join(ODL_OUT, stem, stem + ".json")
    ham = os.path.join(CORPUS, stem + ".pdf")
    if not (os.path.exists(annot) and os.path.exists(jy)):
        return None

    from annot_uret import TUR_RENK, VARSAYILAN_RENK

    mat = pymupdf.Matrix(1.5, 1.5)

    onlar_doc = pymupdf.open(annot)
    if sayfa > onlar_doc.page_count:
        return None
    sol_pix = onlar_doc.load_page(sayfa - 1).get_pixmap(matrix=mat)
    onlar_doc.close()

    biz_doc = pymupdf.open(ham)
    pg = biz_doc.load_page(sayfa - 1)
    H = pg.rect.height
    for o in ogeleri_topla(jy):
        if o["sayfa"] != sayfa:
            continue
        r = TUR_RENK.get(o["tur"], VARSAYILAN_RENK).lstrip("#")
        renk = tuple(int(r[i:i + 2], 16) / 255 for i in (0, 2, 4))
        x0, y0, x1, y1 = o["kutu"]
        pg.draw_rect(pymupdf.Rect(x0, H - y1, x1, H - y0), color=renk, width=1.1)
    sag_pix = pg.get_pixmap(matrix=mat)
    biz_doc.close()

    os.makedirs(CIKTI, exist_ok=True)
    yol = os.path.join(CIKTI, f"{stem}_s{sayfa}_onlar_vs_biz.png")
    genis = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(
        0, 0, sol_pix.width + sag_pix.width + 16, max(sol_pix.height, sag_pix.height)))
    genis.set_rect(genis.irect, (255, 255, 255))
    sol_pix.set_origin(0, 0)
    genis.copy(sol_pix, sol_pix.irect)
    sag_pix.set_origin(sol_pix.width + 16, 0)
    genis.copy(sag_pix, sag_pix.irect)
    genis.save(yol)
    return yol


def main() -> None:
    tek = None
    if "--belge" in sys.argv:
        tek = sys.argv[sys.argv.index("--belge") + 1]
    sayfa = 1
    if "--sayfa" in sys.argv:
        sayfa = int(sys.argv[sys.argv.index("--sayfa") + 1])

    print("KONTROL 1 — HTML'deki her kutu JSON'dan yeniden hesaplanabiliyor mu?")
    print("-" * 68)
    hepsi_tamam = True
    for stem in ([tek] if tek else BELGELER):
        tutan, top = kontrol1(stem)
        if top == 0:
            print(f"  {stem:32} (dosya yok)")
            continue
        durum = "TAMAM" if tutan == top else "UYUSMAZLIK"
        if tutan != top:
            hepsi_tamam = False
        print(f"  {stem:32} {tutan:>5}/{top:<5} kutu   {durum}")
    print("-" * 68)
    print("SONUC:", "her kutu JSON'dan turetilmis, elle eklenmis kutu YOK"
          if hepsi_tamam else "UYUSMAZLIK VAR — incele")

    print("\nKONTROL 2 — onlarin cizimi | bizim cizimimiz")
    print("-" * 68)
    for stem in ([tek] if tek else ["attention_tablo", "vgg_tablo_agirlikli",
                                    "resnet_2sutun_gorsel"]):
        y = kontrol2(stem, sayfa)
        print(f"  {stem:32} {os.path.relpath(y, BASE) if y else '(uretilemedi)'}")


if __name__ == "__main__":
    main()
