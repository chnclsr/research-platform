"""MinerU ciktisini sonuclar.csv'ye 5. parser olarak ekler.

NEDEN AYRI SCRIPT
-----------------
MinerU ayri ortamda (.venv-mineru) kosuyor, compare.py ise ana .venv'de.
compare.py'yi MinerU'yu da kosturacak sekilde degistirsek her seferinde
20 dakikalik tam kosu gerekirdi. Oysa MinerU'nun markdown ciktisi zaten
diskte: out/<belge>__mineru.md ve out/mineru_json/<belge>_content_list.json

Bu script o hazir ciktilari alip compare.py'nin KENDI measure() fonksiyonundan
gecirir. Yani MinerU da digerleriyle AYNI olcum hattindan geciyor -- adalet
kurali korunuyor, sadece ayristirma islemi daha once yapilmis oluyor.

Sureler out/mineru_sureler.json'dan gelir (kalici servis ile olculmus,
servis acilis maliyeti haric).

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\mineru_csv_ekle.py
"""
from __future__ import annotations

import csv
import json
import os
import sys

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
sys.path.insert(0, os.path.join(BASE, "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from compare import measure  # AYNI olcum fonksiyonu -- adalet kurali

OUT = os.path.join(BASE, "out")
MINERU_JSON = os.path.join(OUT, "mineru_json")
CSV_PATH = os.path.join(BASE, "sonuclar.csv")
SURE_JSON = os.path.join(OUT, "mineru_sureler.json")


def sayfa_metinleri(stem: str) -> list[str]:
    """content_list.json'dan sayfa bazli markdown kurar.

    .md dosyasinda sayfa ayraci yok; content_list.json'da her ogenin page_idx'i
    var -> hizalama kesin. mineru_html.py ile ayni mantik.
    """
    yol = os.path.join(MINERU_JSON, f"{stem}_content_list.json")
    if not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        ogeler = json.load(f)
    if not ogeler:
        return []

    kovalar: list[list[str]] = [[] for _ in
                                range(max(o.get("page_idx", 0) for o in ogeler) + 1)]
    for o in ogeler:
        t = o.get("type")
        if t in ("text", "aside_text", "footer", "page_footnote", "page_number"):
            metin = (o.get("text") or "").strip()
            if not metin:
                continue
            sev = o.get("text_level")
            parca = f"{'#' * int(sev)} {metin}" if sev else metin
        elif t == "table":
            bas = " ".join(o.get("table_caption") or [])
            parca = (f"**{bas}**\n\n" if bas else "") + (o.get("table_body") or "")
        elif t in ("image", "chart"):
            bas = o.get("image_caption") or o.get("chart_caption") or []
            parca = " ".join(bas)
        elif t == "equation":
            parca = (o.get("text") or "").strip()
        elif t == "list":
            parca = "\n".join(f"- {x}" for x in (o.get("list_items") or []))
        else:
            parca = (o.get("text") or "").strip()
        if parca:
            kovalar[o.get("page_idx", 0)].append(parca)
    return ["\n\n".join(k) for k in kovalar]


def main() -> None:
    if not os.path.exists(CSV_PATH):
        print("sonuclar.csv yok -- once compare.py kosturulmali")
        return

    sureler = {}
    if os.path.exists(SURE_JSON):
        with open(SURE_JSON, encoding="utf-8") as f:
            sureler = {b["belge"]: b for b in json.load(f).get("belgeler", [])}
    else:
        print("UYARI: out/mineru_sureler.json yok -> sure sutunu bos kalacak")

    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("sonuclar.csv bos")
        return

    eklenen = 0
    for row in rows:
        stem = row["dosya"]
        md_yol = os.path.join(OUT, f"{stem}__mineru.md")
        if not os.path.exists(md_yol):
            print(f"  {stem}: MinerU ciktisi yok, atlandi")
            continue

        with open(md_yol, encoding="utf-8") as f:
            md = f.read()
        pages = sayfa_metinleri(stem)

        row.update(measure("mineru", md, pages))
        s = sureler.get(stem, {})
        row["mineru_sure_sn"] = s.get("sure_sn", "")
        # MinerU'ya ozgu, digerlerinde karsiligi olmayan alanlar
        row["mineru_html_tablo"] = s.get("html_tablo", "")
        row["mineru_yontem"] = s.get("yontem", "")
        eklenen += 1
        print(f"  {stem:30} {len(md):8,} krk  {len(pages):3} sayfa  "
              f"{s.get('sure_sn', '?')} sn")

    if not eklenen:
        print("Hicbir belge islenmedi.")
        return

    # Sutun sirasi: mevcut sutunlar + yeni mineru sutunlari
    alanlar: list[str] = []
    for row in rows:
        for k in row:
            if k not in alanlar:
                alanlar.append(k)

    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=alanlar)
        w.writeheader()
        w.writerows(rows)

    print(f"\n{eklenen} belge icin MinerU sutunlari sonuclar.csv'ye yazildi")
    print(f"  yeni sutun sayisi: {len([a for a in alanlar if a.startswith('mineru')])}")


if __name__ == "__main__":
    main()
