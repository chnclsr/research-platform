"""MinerU sonuclari -> html/mineru.html (indeks) + html/mineru_<belge>.html (her belge)

Mevcut arayuzle AYNI yapida: index.html gibi bir indeks sayfasi + belge basina
ayri sayfa. Ayni CSS degiskenleri, ayni sekme cubugu, ayni dark mode.

HANGI MOD NEREDE  -- karistirilmamali
-------------------------------------
Sayfadaki HER SEY  backend=pipeline (CPU) ciktisidir:
  yan yana karsilastirma, 9 belgenin sureleri, tablo sayilari, OCR sonucu.
  = PP-DocLayoutV2 (215 MB) + SlanetPlus tablo (7.8 MB ONNX)
    + PaddleOCR v6 (OCR buradan geliyor) + unimernet formul
  OmniDocBench v1.6: 86.47 (onlarin yayinladigi)

TEK ISTISNA: "pipeline vs 1.2B VLM" uc yonlu tablosu.
  O tek sayfa (resnet s.6) backend=hybrid-engine ile, MINERU_DEVICE_MODE=cpu
  zorlanarak kosuldu. Model: MinerU2.5-Pro-2605-1.2B.
  OmniDocBench v1.6: 95.26-95.69. NVIDIA Volta+ 8 GB VRAM ister; bu makinede yok.

OCR NOTU: taranmis belgeden cikan 24.554 karakter PIPELINE modundan geliyor,
VLM'den degil. Yani OCR yetenegi GPU'suz yolda da elimizde.

ADALET KURALI
-------------
Butun parser ciktilari AYNI markdown kutuphanesinden ayni ayarlarla gecer
(html_uret.render). MinerU'nun tablolari HTML parcasi olarak geliyor; markdown
kutuphanesi ham HTML'i aynen gecirir -- ayricalik degil, gercek cikti.
MinerU'nun kendi _layout.pdf / _span.pdf dosyalari karsilastirmada KULLANILMAZ,
"kiyas disi" etiketiyle ayri baglanti olarak durur.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\mineru_html.py
    .\\.venv\\Scripts\\python.exe src\\mineru_html.py --only resnet
    .\\.venv\\Scripts\\python.exe src\\mineru_html.py --indeks   (sadece indeks)
"""
from __future__ import annotations

import csv
import html as ihtml
import json
import os
import re
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
sys.path.insert(0, os.path.join(BASE, "src"))

import html_uret as HU
import pdf_inspector

CORPUS = os.path.join(BASE, "corpus")
OUT = os.path.join(BASE, "out")
HTML_DIR = os.path.join(BASE, "html")
MINERU_JSON = os.path.join(OUT, "mineru_json")
MINERU_OUT = os.path.join(OUT, "mineru")
MINERU_ASSETS = os.path.join(HTML_DIR, "assets", "mineru")

HYBRID_JSON = os.path.join(
    OUT, "mineru_hybrid", "resnet_2sutun_gorsel", "hybrid_auto",
    "resnet_2sutun_gorsel_content_list.json")
HYBRID_SURE_SN = 145        # 10:53:28 -> 10:55:53, tek sayfa, log'dan okundu
HYBRID_MODEL_YUK_SN = 84.5  # "get transformers predictor cost: 84.5s"

BELGELER = [
    ("attention_tablo", "4 tablo, 2 sütun"),
    ("bert_2sutun_dipnot", "2 sütun + dipnot"),
    ("vgg_tablo_agirlikli", "tablo ağırlıklı"),
    ("resnet_2sutun_gorsel", "çok görsel + diyagram sayfası"),
    ("gpt3_uzun_75sayfa", "75 sayfa"),
    ("gpt4_uzun_gorsel", "100 sayfa, çok görsel"),
    ("sybil_tip_2sutun", "tıp, 2 sütun"),
    ("turkce_makale", "Türkçe karakter"),
    ("taranmis_bert_2sutun_dipnot", "TARANMIŞ — metin katmanı yok"),
]


# ======================================================================
#  MinerU content_list.json -> sayfa bazli markdown
# ======================================================================

def mineru_sayfalar(stem: str) -> tuple[list[str], dict]:
    """content_list.json'dan sayfa bazli markdown kurar.

    .md dosyasini bolmuyoruz cunku sayfa ayraci yok. content_list.json'da her
    ogenin page_idx'i var -> hizalama KESIN, tahmin degil.
    """
    yol = os.path.join(MINERU_JSON, f"{stem}_content_list.json")
    if not os.path.exists(yol):
        return [], {}
    with open(yol, encoding="utf-8") as f:
        ogeler = json.load(f)
    if not ogeler:
        return [], {}

    from collections import Counter
    tipler = Counter(o.get("type") for o in ogeler)
    kovalar: list[list[str]] = [[] for _ in
                                range(max(o.get("page_idx", 0) for o in ogeler) + 1)]

    for o in ogeler:
        t = o.get("type")
        parca = ""

        if t in ("text", "aside_text", "footer", "page_footnote", "page_number"):
            metin = (o.get("text") or "").strip()
            if not metin:
                continue
            sev = o.get("text_level")
            parca = f"{'#' * int(sev)} {metin}" if sev else metin

        elif t == "table":
            bas = o.get("table_caption") or []
            dip = o.get("table_footnote") or []
            p = []
            if bas:
                p.append("**" + " ".join(bas) + "**")
            p.append(o.get("table_body") or "")
            if dip:
                p.append("_" + " ".join(dip) + "_")
            parca = "\n\n".join(x for x in p if x)

        elif t in ("image", "chart"):
            bas = o.get("image_caption") or o.get("chart_caption") or []
            p = []
            if o.get("img_path"):
                p.append(f"![]({_gorsel_url(stem, o['img_path'])})")
            if bas:
                p.append(" ".join(bas))
            if o.get("content"):
                p.append(str(o["content"]))
            parca = "\n\n".join(p)

        elif t == "equation":
            parca = (o.get("text") or "").strip()

        elif t == "list":
            parca = "\n".join(f"- {x}" for x in (o.get("list_items") or []))

        else:
            parca = (o.get("text") or "").strip()

        if parca:
            kovalar[o.get("page_idx", 0)].append(parca)

    return ["\n\n".join(k) for k in kovalar], dict(tipler)


def _gorsel_url(stem: str, img_path: str) -> str:
    return f"assets/mineru/{stem}/{os.path.basename(img_path)}"


def gorselleri_kopyala(stem: str) -> int:
    kok = os.path.join(MINERU_OUT, stem)
    if not os.path.isdir(kok):
        return 0
    kaynak = next((os.path.join(kok, d, "images") for d in os.listdir(kok)
                   if os.path.isdir(os.path.join(kok, d, "images"))), None)
    if not kaynak:
        return 0
    hedef = os.path.join(MINERU_ASSETS, stem)
    os.makedirs(hedef, exist_ok=True)
    n = 0
    for fn in os.listdir(kaynak):
        if fn.lower().endswith((".jpg", ".jpeg", ".png")):
            h = os.path.join(hedef, fn)
            if not os.path.exists(h):
                shutil.copyfile(os.path.join(kaynak, fn), h)
            n += 1
    return n


def mineru_ek_ciktilar(stem: str) -> dict[str, tuple[str, int]]:
    """KIYAS DISI dosyalar: _layout.pdf / _span.pdf / *.json / .md"""
    kok = os.path.join(MINERU_OUT, stem)
    if not os.path.isdir(kok):
        return {}
    yontem = next((d for d in os.listdir(kok)
                   if os.path.isdir(os.path.join(kok, d))), None)
    if not yontem:
        return {}
    kaynak_dir = os.path.join(kok, yontem)
    hedef = os.path.join(MINERU_ASSETS, stem)
    os.makedirs(hedef, exist_ok=True)

    bulunan = {}
    for etiket, ek in [("düzen kutuları (PDF)", "_layout.pdf"),
                       ("span kutuları (PDF)", "_span.pdf"),
                       ("öğe listesi (JSON)", "_content_list.json"),
                       ("tam düzen (JSON)", "_middle.json"),
                       ("ham markdown", ".md")]:
        ad = f"{stem}{ek}"
        kaynak = os.path.join(kaynak_dir, ad)
        if os.path.exists(kaynak):
            h = os.path.join(hedef, ad)
            if not os.path.exists(h) or os.path.getsize(h) != os.path.getsize(kaynak):
                shutil.copyfile(kaynak, h)
            bulunan[etiket] = (f"assets/mineru/{stem}/{ad}",
                               os.path.getsize(kaynak))
    return bulunan


# ======================================================================
#  TABLO HUCRE DOGRULUGU
# ======================================================================
# Bu degerler corpus/resnet_2sutun_gorsel.pdf sayfa 6'nin metninden BIREBIR
# okunarak dogrulandi (uydurulmadi):
#   "PReLU-net [13] 4.94 BN-inception [16] 4.82 ResNet (ILSVRC'15) 3.57"
GERCEK_TABLO5 = [
    ("VGG [41] (ILSVRC'14)", "7.32"),
    ("GoogLeNet [44] (ILSVRC'14)", "6.66"),
    ("VGG [41] (v5)", "6.8"),
    ("PReLU-net [13]", "4.94"),
    ("BN-inception [16]", "4.82"),
    ("ResNet (ILSVRC'15)", "3.57"),
]


def tablo_satirlari(govde: str) -> list[list[str]]:
    satirlar = []
    for tr in re.findall(r"<tr>(.*?)</tr>", govde, re.S):
        satirlar.append([re.sub(r"<[^>]+>", "", h).strip()
                         for h in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)])
    return satirlar


def _sadelestir(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _tablolar(yol_veya_stem: str, sayfa: int | None = None) -> list[str]:
    """Tablo govdelerini dondurur. sayfa verilirse o sayfayla sinirlar."""
    yol = (yol_veya_stem if yol_veya_stem.endswith(".json")
           else os.path.join(MINERU_JSON, f"{yol_veya_stem}_content_list.json"))
    if not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        ogeler = json.load(f)
    return [o.get("table_body") or "" for o in ogeler
            if o.get("type") == "table"
            and (sayfa is None or o.get("page_idx") == sayfa - 1)]


def _tablo5_satirlari(govdeler: list[str]) -> list[list[str]]:
    """Table 5'i ICERIGINE gore bulur -- basliga guvenmez.

    Neden: hybrid ciktisinda basliklar bir kaydi (ilk tablonun basligi yok,
    ikincisi 'Table 3' etiketi almis). Icerik esasli arama daha saglam.
    """
    for govde in govdeler:
        satirlar = [s for s in tablo_satirlari(govde) if any(s)]
        duz = " ".join(" ".join(s) for s in satirlar)
        if "7.32" in duz and "6.66" in duz and "3.57" in duz:
            if satirlar and "method" in " ".join(satirlar[0]).lower():
                satirlar = satirlar[1:]
            return satirlar
    return []


def uc_yonlu_tablo5() -> str:
    pl = _tablo5_satirlari(_tablolar("resnet_2sutun_gorsel", 6))
    hy = _tablo5_satirlari(_tablolar(HYBRID_JSON))
    if not hy:
        return ('<p class="bos">hybrid koşusu bulunamadı '
                "(out/mineru_hybrid altında content_list.json yok).</p>")

    def hucre(satirlar, i, g_ad, g_deger):
        s = satirlar[i] if i < len(satirlar) else []
        # HTML varliklari KARSILASTIRMADAN ONCE cozulmeli. Aksi halde &#x27;
        # -> _sadelestir icinde "x27" olarak metne karisir ve dogru satiri
        # yanlis gosterir. Bu hata bir kez yasandi, duzeltildi.
        ad = ihtml.unescape(s[0]) if s else "(satır yok)"
        deger = ihtml.unescape(s[1]) if len(s) > 1 else "(boş)"
        ok = (_sadelestir(g_ad) in _sadelestir(ad)
              and g_deger.replace(" ", "") == deger.replace(" ", ""))
        # birlesmis etiket: beklenenden COK daha uzunsa isaretle
        birlesik = ok and len(_sadelestir(ad)) > len(_sadelestir(g_ad)) * 1.6
        sinif = "hbirlesik" if birlesik else ("hok" if ok else "hhata")
        im = "~" if birlesik else ("✓" if ok else "✗")
        return (f'<td class="{sinif}">{im} {ihtml.escape(ad)}</td>'
                f'<td class="{sinif}"><b>{ihtml.escape(deger)}</b></td>'), ok, birlesik

    tr, pl_ok, hy_ok, pl_bir = [], 0, 0, 0
    n = max(len(GERCEK_TABLO5), len(pl), len(hy))
    for i in range(n):
        g_ad, g_deger = GERCEK_TABLO5[i] if i < len(GERCEK_TABLO5) else ("—", "—")
        ph, pi, pb = hucre(pl, i, g_ad, g_deger)
        hh, hi, _hb = hucre(hy, i, g_ad, g_deger)
        pl_ok += pi
        pl_bir += pb
        hy_ok += hi
        tr.append(f"<tr><td>{ihtml.escape(g_ad)}</td>"
                  f"<td><b>{ihtml.escape(g_deger)}</b></td>{ph}{hh}</tr>")

    bir_not = (f' <span class="kucuk">({pl_bir} tanesi <b>~</b> — etiket '
               f"birleşmiş, cömert eşleşme)</span>" if pl_bir else "")
    return f"""
<table class="kars uc">
<thead>
<tr><th colspan="2">GERÇEK — PDF'ten doğrulandı</th>
    <th colspan="2">pipeline · SlanetPlus 7,8 MB ONNX · CPU</th>
    <th colspan="2">hybrid · MinerU2.5-Pro <b>1,2B VLM</b></th></tr>
<tr><th>satır</th><th>top-5</th><th>satır</th><th>top-5</th>
    <th>satır</th><th>top-5</th></tr></thead>
<tbody>{''.join(tr)}</tbody>
<tfoot><tr><th colspan="2">doğru satır</th>
<th colspan="2" class="{'hhata' if pl_ok < n else 'hok'}">{pl_ok} / {n}{bir_not}</th>
<th colspan="2" class="{'hhata' if hy_ok < n else 'hok'}">{hy_ok} / {n}</th>
</tr></tfoot></table>"""


# ======================================================================
#  VERI OKUMA
# ======================================================================

# ======================================================================
#  SUPHELI TABLO HUCRESI ISARETLEME
# ======================================================================
# NEDEN GEREKLI: satiri yanlis olan bir tablo GORSEL OLARAK KUSURSUZ gorunur.
# resnet s.6 Table 5'te "ResNet (ILSVRC'15) -> 4.82" yaziyor (dogrusu 3.57) ama
# tablo duzgun bicimli oldugu icin goz bunu yakalamiyor. Sutun sayisi da tutarli,
# yani mevcut _tablo_uyari hic tetiklenmiyor (olculdu: 0 uyari).
#
# Asagidaki uc kural, ELDE GERCEK DEGER OLMADAN da bu hata desenini yakalar.
# Kesin degildir -- "buraya bak" der, "burasi yanlis" demez.

_SAYI = re.compile(r"(?<![\w.])\d+[.,]?\d*(?![\w.])")


def tablo_supheleri(h: str) -> str:
    """MinerU sutunundaki tablolara otomatik supheli-hucre isareti ekler."""

    def isle(m):
        blok = m.group(0)
        satirlar = re.findall(r"<tr>(.*?)</tr>", blok, re.S)
        bulgular = []

        for idx, tr in enumerate(satirlar):
            hucreler = [re.sub(r"<[^>]+>", "", x).strip()
                        for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            if not hucreler or idx == 0:      # baslik satirini atla
                continue

            # 1) veri satirinda etiket hucresi bos -> satir kaymis olabilir
            if hucreler[0] == "" and any(x for x in hucreler[1:]):
                bulgular.append(f"satır {idx}: <b>etiket hücresi boş</b> "
                                f"(değer var: {ihtml.escape(hucreler[1][:20])})")

            # 2) tek hucrede birden fazla sayi -> iki satirin degeri birlesmis
            for j, hu in enumerate(hucreler[1:], 1):
                if len(_SAYI.findall(hu)) > 1:
                    bulgular.append(f"satır {idx}, sütun {j}: "
                                    f"<b>tek hücrede {len(_SAYI.findall(hu))} sayı</b> "
                                    f"— “{ihtml.escape(hu[:26])}”")

            # 3) etiket hucresinde birden fazla kaynak referansi -> etiket birlesmis
            if len(re.findall(r"\[\d+\]", hucreler[0])) > 1:
                bulgular.append(f"satır {idx}: <b>etiket birleşmiş</b> "
                                f"— “{ihtml.escape(hucreler[0][:34])}”")

        if not bulgular:
            return blok
        liste = "".join(f"<li>{b}</li>" for b in bulgular[:6])
        art = (f"<li>… ve {len(bulgular) - 6} tane daha</li>"
               if len(bulgular) > 6 else "")
        return (f'<div class="tbl-suphe"><b>⚠ {len(bulgular)} şüpheli hücre</b>'
                f" — satır hizası kaymış olabilir<ul>{liste}{art}</ul></div>{blok}")

    return re.sub(r"<table>.*?</table>", isle, h, flags=re.S)


def sonuclar_csv() -> dict[str, dict]:
    yol = os.path.join(BASE, "sonuclar.csv")
    if not os.path.exists(yol):
        return {}
    with open(yol, encoding="utf-8-sig", newline="") as f:
        return {r["dosya"]: r for r in csv.DictReader(f)}


def mineru_sureler() -> dict[str, dict]:
    yol = os.path.join(OUT, "mineru_sureler.json")
    if not os.path.exists(yol):
        return {}
    with open(yol, encoding="utf-8") as f:
        return {b["belge"]: b for b in json.load(f).get("belgeler", [])}


CSV_D = sonuclar_csv()
MN_D = mineru_sureler()


def sayfa_sayisi(stem: str) -> int:
    try:
        return int(CSV_D.get(stem, {}).get("insp_sayfa_sayisi")
                   or MN_D.get(stem, {}).get("sayfa") or 0)
    except (TypeError, ValueError):
        return 0


# ======================================================================
#  TABLOLAR
# ======================================================================

def _fmt(v, basamak=2, bin_ayrac=False):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    if bin_ayrac:
        return f"{int(f):,}".replace(",", ".")
    return f"{f:.{basamak}f}"


def ozet_tablo() -> str:
    satir = []
    for stem, _n in BELGELER:
        c, m = CSV_D.get(stem, {}), MN_D.get(stem, {})
        sinif = ' class="taranmis"' if stem.startswith("taranmis") else ""
        satir.append(f"""<tr{sinif}>
<td class="bel"><a href="mineru_{stem}.html">{stem}</a></td>
<td>{sayfa_sayisi(stem) or '?'}</td>
<td>{_fmt(c.get('inspector_karakter'), bin_ayrac=True)}</td>
<td>{_fmt(c.get('opendataloader_karakter'), bin_ayrac=True)}</td>
<td>{_fmt(c.get('pymupdf4llm_karakter'), bin_ayrac=True)}</td>
<td class="mn">{_fmt(m.get('karakter'), bin_ayrac=True)}</td>
<td class="mn">{m.get('html_tablo', '—')}</td>
<td class="mn">{_fmt(m.get('sure_sn'))}</td></tr>""")
    return f"""<table class="ozet">
<thead><tr><th>belge</th><th>sayfa</th><th>inspector<br><span class="kucuk">karakter</span></th>
<th>opendataloader<br><span class="kucuk">karakter</span></th>
<th>pymupdf4llm<br><span class="kucuk">karakter</span></th>
<th class="mn">MinerU<br><span class="kucuk">karakter</span></th>
<th class="mn">MinerU<br><span class="kucuk">tablo</span></th>
<th class="mn">MinerU<br><span class="kucuk">sn</span></th></tr></thead>
<tbody>{''.join(satir)}</tbody></table>"""


def hiz_tablosu() -> str:
    motorlar = [("pypdf", "pypdf_plain_sure_sn"),
                ("inspector", "inspector_sure_sn"),
                ("opendataloader", "opendataloader_sure_sn"),
                ("pymupdf4llm", "pymupdf4llm_sure_sn")]
    veri: dict[str, list[float]] = {ad: [] for ad, _ in motorlar}
    veri["MinerU pipeline (CPU)"] = []
    satir = []

    for stem, _n in BELGELER:
        sy = sayfa_sayisi(stem)
        if not sy:
            continue
        c, m = CSV_D.get(stem, {}), MN_D.get(stem, {})
        h = [f'<td class="bel">{stem}</td><td>{sy}</td>']
        for ad, alan in motorlar:
            try:
                v = float(c[alan]) / sy
                veri[ad].append(v)
                h.append(f"<td>{v:.3f}</td>")
            except (KeyError, TypeError, ValueError):
                h.append("<td>—</td>")
        if m.get("sure_sn"):
            v = m["sure_sn"] / sy
            veri["MinerU pipeline (CPU)"].append(v)
            h.append(f'<td class="mn">{v:.2f}</td>')
        else:
            h.append('<td class="mn">—</td>')
        satir.append("<tr>" + "".join(h) + "</tr>")

    ort = {k: sum(v) / len(v) for k, v in veri.items() if v}
    ort["MinerU hybrid · 1,2B VLM (CPU)"] = float(HYBRID_SURE_SN)
    taban, tavan = min(ort.values()), max(ort.values())

    cub = []
    for k, v in sorted(ort.items(), key=lambda x: x[1]):
        kat = f"{v / taban:,.0f}".replace(",", ".")
        cub.append(f'<div class="cs"><div class="cad">{ihtml.escape(k)}</div>'
                   f'<div class="cbar"><span style="width:'
                   f'{max(0.4, 100 * v / tavan):.2f}%"></span></div>'
                   f'<div class="cdeg">{v:.3f} sn/sayfa '
                   f'<span class="kat">{kat}×</span></div></div>')

    bas = "".join(f"<th>{ad}</th>" for ad, _ in motorlar)
    return f"""<table class="ozet"><thead>
<tr><th>belge</th><th>sayfa</th>{bas}<th class="mn">MinerU pipeline</th></tr>
<tr><th colspan="2"></th><th colspan="5" class="kucuk">saniye / sayfa</th></tr>
</thead><tbody>{''.join(satir)}</tbody></table>
<h3>Ortalama sn/sayfa — en hızlıya göre kaç kat</h3>
<div class="cubuklar">{''.join(cub)}</div>"""


def oge_tipleri_tablo() -> str:
    b = []
    for stem, _n in BELGELER:
        _, tipler = mineru_sayfalar(stem)
        if not tipler:
            continue
        h = " ".join(f'<span class="tip"><b>{v}</b> {ihtml.escape(k)}</span>'
                     for k, v in sorted(tipler.items(), key=lambda x: -x[1]))
        b.append(f'<div class="tipsatir"><div class="bel">{stem}</div><div>{h}</div></div>')
    return "".join(b)


# ======================================================================
#  CSS  -- mevcut sayfalarla AYNI degisken sistemi + dark mode
# ======================================================================

CSS = """
:root{--bg:#f6f7f9;--kart:#fff;--metin:#1c1f23;--soluk:#6b7280;--cizgi:#e3e6ea;
--vurgu:#b4451f;--vurgu-bg:#fdf4f0;--uyari:#8a5a00;--uyari-bg:#fff8e6;--kod-bg:#f2f3f5;
--yuksek:#c0392b;--orta:#b8860b;--dusuk:#5f8a5f;
--iyi:#1e8449;--iyi-bg:#eaf7ef;--hata-bg:#fdecea;--mn-bg:#eef4fd;--bar:#2c5aa0}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#14171a;--kart:#1c2024;--metin:#e6e8ea;--soluk:#9aa3ad;--cizgi:#2c3238;
--vurgu:#ff9f7a;--vurgu-bg:#2a1d17;--uyari:#e8c37a;--uyari-bg:#2a2312;--kod-bg:#24282d;
--yuksek:#ff8a7a;--orta:#e8c37a;--dusuk:#8fbf8f;
--iyi:#7fd1a0;--iyi-bg:#16281d;--hata-bg:#2e1a18;--mn-bg:#1a2230;--bar:#5b9bd5}}
:root[data-theme="dark"]{
--bg:#14171a;--kart:#1c2024;--metin:#e6e8ea;--soluk:#9aa3ad;--cizgi:#2c3238;
--vurgu:#ff9f7a;--vurgu-bg:#2a1d17;--uyari:#e8c37a;--uyari-bg:#2a2312;--kod-bg:#24282d;
--yuksek:#ff8a7a;--orta:#e8c37a;--dusuk:#8fbf8f;
--iyi:#7fd1a0;--iyi-bg:#16281d;--hata-bg:#2e1a18;--mn-bg:#1a2230;--bar:#5b9bd5}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--metin);
font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif}
.ust{position:sticky;top:0;z-index:20;display:flex;justify-content:space-between;
align-items:center;gap:16px;padding:10px 18px;background:var(--kart);
border-bottom:1px solid var(--cizgi);flex-wrap:wrap}
.ust-sol{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.kucuk{color:var(--soluk);font-size:13px;font-weight:400}
.sekmeler{display:flex;gap:4px;margin-right:6px}
.sekmeler a{padding:5px 14px;border-radius:8px;text-decoration:none;
color:var(--metin);border:1px solid var(--cizgi);font-size:14px}
.sekmeler a:hover{border-color:var(--vurgu);color:var(--vurgu)}
.sekmeler a.aktif-sekme{background:var(--vurgu);color:#fff;border-color:var(--vurgu)}
.geri{color:var(--vurgu);text-decoration:none;font-weight:600}
.giris{margin:18px;max-width:960px}
.giris p{margin:0 0 10px}
h2{font-size:18px;margin:30px 18px 8px;padding-bottom:6px;
border-bottom:2px solid var(--cizgi)}
h3{font-size:15px;margin:22px 18px 6px}
p.aciklama{margin:0 18px 10px;color:var(--soluk);font-size:13.5px;max-width:960px}
code{background:var(--kod-bg);padding:1px 5px;border-radius:3px;font-size:12.5px}
a{color:var(--vurgu)}
.uyari-kutu{margin:12px 18px;padding:12px 16px;background:var(--uyari-bg);
border:1px solid var(--uyari);border-radius:10px;font-size:13.5px;max-width:1100px}
.uyari-kutu ul{margin:6px 0 0;padding-left:20px}.uyari-kutu li{margin:3px 0}
.kritik{background:var(--hata-bg);border-color:var(--yuksek)}
.iyi-kutu{background:var(--iyi-bg);border-color:var(--iyi)}
table{border-collapse:collapse;background:var(--kart);font-size:13px;
margin:0 18px;border:1px solid var(--cizgi);border-radius:10px;overflow:hidden}
th,td{padding:6px 10px;border-bottom:1px solid var(--cizgi);text-align:right}
th{background:var(--kod-bg);font-weight:600;font-size:12px;text-align:center}
td.bel{text-align:left;font-family:ui-monospace,Consolas,monospace;font-size:12px}
td.mn,th.mn{background:var(--mn-bg)}
tr.taranmis td{background:var(--uyari-bg)}
.kars td,.kars th{text-align:left}
.kars tfoot th{text-align:center;font-size:14px}
td.hok{background:var(--iyi-bg);color:var(--iyi)}
th.hok{background:var(--iyi-bg);color:var(--iyi)}
td.hhata,th.hhata{background:var(--hata-bg);color:var(--yuksek);font-weight:600}
td.hbirlesik{background:var(--uyari-bg);color:var(--uyari)}
.cubuklar{margin:8px 18px;padding:12px 14px;background:var(--kart);
border:1px solid var(--cizgi);border-radius:10px;max-width:1100px}
.cs{display:grid;grid-template-columns:250px 1fr 200px;gap:10px;
align-items:center;padding:4px 0}
.cad{font-size:12.5px;text-align:right;color:var(--metin)}
.cbar{background:var(--kod-bg);border-radius:3px;height:16px;overflow:hidden}
.cbar span{display:block;height:100%;background:var(--bar)}
.cdeg{font-size:12px;font-family:ui-monospace,Consolas,monospace}
.kat{color:var(--yuksek);font-weight:600;margin-left:6px}
.tipsatir{display:flex;gap:14px;align-items:baseline;margin:0 18px;padding:5px 0;
border-bottom:1px solid var(--cizgi)}
.tipsatir .bel{min-width:250px;font-family:ui-monospace,Consolas,monospace;font-size:12px}
.tip{display:inline-block;background:var(--kart);border:1px solid var(--cizgi);
border-radius:10px;padding:1px 8px;margin:2px 3px 2px 0;font-size:12px}
.kartlar{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));
gap:12px;margin:18px}
.kart{display:flex;flex-direction:column;gap:4px;padding:16px;background:var(--kart);
border:1px solid var(--cizgi);border-radius:10px;color:var(--metin)}
.kart > a{text-decoration:none;color:var(--metin);font-size:15px}
.kart:hover{border-color:var(--vurgu)}
.kart span{color:var(--soluk);font-size:13px}
.kart .alt-bag{margin-top:6px;font-size:12.5px;color:var(--vurgu);text-decoration:none}
.kart .alt-bag:hover{text-decoration:underline}
.ekler{margin:12px 18px;padding:10px 14px;background:var(--kart);
border:1px solid var(--cizgi);border-radius:10px;font-size:12.5px;max-width:1100px}
.kiyasdisi{background:var(--soluk);color:var(--kart);border-radius:3px;
padding:1px 6px;font-size:10px;letter-spacing:.4px;margin-left:8px}
.sayfa-nav{padding:8px 18px;color:var(--soluk);font-size:13px;line-height:2}
.sayfa-nav a{display:inline-block;margin-right:5px;padding:2px 8px;
border:1px solid var(--cizgi);border-radius:6px;color:var(--metin);text-decoration:none}
.sayfa-nav a.yuksek{border-color:var(--yuksek);color:var(--yuksek);font-weight:600}
.sayfa-nav a:hover{border-color:var(--vurgu);color:var(--vurgu)}
.sblok{margin:14px 18px;background:var(--kart);border:1px solid var(--cizgi);
border-radius:10px;overflow:hidden}
.sbas{background:var(--kod-bg);padding:6px 12px;font-size:13px;font-weight:600;
display:flex;justify-content:space-between}
.sbas .puan{font-weight:400;color:var(--soluk)}
.uclu{display:grid;grid-template-columns:1fr 1fr 1fr}
.kol{padding:10px 12px;border-left:1px solid var(--cizgi);min-width:0}
.kol:first-child{border-left:0}
.mnkol{background:var(--mn-bg)}
.kbas{font-size:11px;font-weight:600;color:var(--soluk);text-transform:uppercase;
letter-spacing:.4px;margin-bottom:7px;padding-bottom:4px;
border-bottom:1px solid var(--cizgi)}
.kbas .alt{display:block;font-weight:400;text-transform:none;letter-spacing:0;font-size:11px}
.kol img{width:100%;border:1px solid var(--cizgi);border-radius:4px}
.md{font-size:12.5px;max-height:600px;overflow:auto;word-wrap:break-word}
.md table{font-size:11px;margin:8px 0;border-radius:4px}
.md th,.md td{padding:3px 5px;text-align:left}
.md img{max-width:100%;height:auto}
.md h1,.md h2,.md h3,.md h4{font-size:13px;margin:9px 0 4px;border:0;padding:0}
.bos{color:var(--soluk);font-style:italic;font-size:12px}
.tbl-uyari{background:var(--hata-bg);color:var(--yuksek);font-size:11px;
padding:3px 6px;border-radius:3px;margin:4px 0}
.tbl-suphe{background:var(--uyari-bg);border:1px solid var(--uyari);
color:var(--uyari);font-size:11px;padding:5px 8px;border-radius:5px;margin:6px 0 2px}
.tbl-suphe ul{margin:4px 0 0;padding-left:16px}
.tbl-suphe li{margin:1px 0}
.tbl-suphe b{color:var(--yuksek)}
@media(max-width:1100px){.uclu{grid-template-columns:1fr}
.kol{border-left:0;border-top:1px solid var(--cizgi)}
.cs{grid-template-columns:1fr}.cad{text-align:left}}
"""


def _sekmeler(aktif: bool) -> str:
    a = ' class="aktif-sekme"' if aktif else ""
    return ('<nav class="sekmeler"><a href="index.html">Belgeler</a>'
            '<a href="annot_index.html">Etiketli görünüm</a>'
            '<a href="olcumler.html">Ölçümler</a>'
            f'<a href="mineru.html"{a}>MinerU</a></nav>')


MOD_UYARI = """
<div class="uyari-kutu kritik">
<b>Hangi mod ölçüldü — karıştırmamak için</b>
<ul>
<li><b>Bu sayfadaki her şey <code>backend=pipeline</code> (CPU) çıktısıdır:</b>
    yan yana karşılaştırma, süreler, tablo sayıları ve
    <b>taranmış belgedeki OCR sonucu da dahil.</b>
    PP-DocLayoutV2 (215 MB) + <b>SlanetPlus tablo (7,8 MB ONNX)</b> +
    PaddleOCR v6 + unimernet. OmniDocBench v1.6: <b>86,47</b></li>
<li><b>Tek istisna:</b> "pipeline vs 1,2B VLM" üç yönlü tablosu.
    O tek sayfa (<code>resnet</code> s.6) <code>hybrid-engine</code> +
    <code>MINERU_DEVICE_MODE=cpu</code> ile koşuldu.
    Model: <code>MinerU2.5-Pro-2605-1.2B</code>. OmniDocBench v1.6:
    <b>95,26–95,69</b>. Normalde NVIDIA Volta+ 8 GB VRAM ister;
    bu makinede <b>NVIDIA GPU yok</b> (Intel UHD 770).</li>
<li><b>OCR notu:</b> taranmış belgeden çıkan 24.554 karakter
    <b>pipeline</b>'dan geliyor, VLM'den değil. Yani OCR yeteneği
    <b>GPU'suz yolda da elimizde.</b></li>
</ul>
</div>"""


def indeks_html() -> str:
    kartlar = []
    for stem, notu in BELGELER:
        m = MN_D.get(stem, {})
        sy = sayfa_sayisi(stem)
        kartlar.append(
            f'<div class="kart"><a href="mineru_{stem}.html"><strong>{stem}</strong></a>'
            f'<span>{sy} sayfa · {m.get("html_tablo", "—")} tablo · '
            f'{_fmt(m.get("sure_sn"))} sn</span>'
            f'<span class="kucuk">{ihtml.escape(notu)}</span>'
            f'<a class="alt-bag" href="{stem}.html">4 parser karşılaştırması →</a>'
            f'<a class="alt-bag" href="annot_{stem}.html">'
            f'opendataloader etiketli görünüm →</a></div>')

    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MinerU — ölçüm ve inceleme</title><style>{CSS}</style></head><body>
<div class="ust"><div class="ust-sol">{_sekmeler(True)}
<strong>MinerU 3.4.4</strong>
<span class="kucuk">pipeline (CPU) · 9 belge · 261 sayfa ·
ayrı <code>.venv-mineru</code></span></div></div>

<div class="giris">
<p><b>Belge seç, tüm sayfalarını gör.</b> Her belge sayfasında solda gerçek PDF
görüntüsü, ortada pdf-inspector, sağda MinerU — belgenin <b>bütün</b> sayfaları,
seçim yapılmadan.</p>
</div>

{MOD_UYARI}

<div class="uyari-kutu">
<b>Süreler artık temiz koşudan — ama oynaklık gerçek bir bulgu.</b><br>
Bütün süreler makine boşken, başka hiçbir ölçüm çalışmazken yeniden alındı
(<code>compare.py</code> 3 koşunun medyanını alır). Önceki sürümde
"paralel işlerim yüzünden şişmiş" demiştim — <b>bu yanlıştı</b>: temiz koşuda
bazı süreler düştü, bazıları <i>çıktı</i>. Yani kirlenme tek açıklama değil.
<br><br>Ölçülen oynaklık, iki temiz koşu arasında:
<ul>
<li><code>opendataloader</code> — <b>%2–5</b>, çok kararlı</li>
<li><code>pdf-inspector</code> — kararlı (sayılar milisaniye seviyesinde)</li>
<li><b><code>pymupdf4llm</code> — 3–4 kat</b> (attention 8,6 → 33,4 sn;
    resnet 38,0 → 11,8 sn). Hem artı hem eksi yönde.</li>
<li><code>MinerU pipeline</code> — <b>±%50</b> (attention 167,8 → 96,5;
    vgg 75,6 → 113,3)</li>
</ul>
inspector ve opendataloader aynı koşuda kararlı çıktığına göre sorun makine
değil, kütüphanelerin kendisi. <b>Öngörülemeyen süre, 900 saniyelik toplama
bütçesinde gerçek bir risktir</b> — tek sayı yerine aralık okunmalı.
</div>

<div class="uyari-kutu">
<b>Adalet kuralı</b> — bütün parser çıktıları <b>aynı</b> markdown
kütüphanesinden aynı ayarlarla geçti. MinerU'nun tabloları HTML parçası olarak
geliyor; markdown kütüphanesi ham HTML'i aynen geçirdiği için tablo olarak
görünüyor — bu ayrıcalık değil, MinerU'nun gerçek çıktısı. MinerU'nun kendi
<code>_layout.pdf</code> / <code>_span.pdf</code> dosyaları karşılaştırmada
<b>kullanılmadı</b>; her belge sayfasında "kıyas dışı" etiketiyle duruyor.
</div>

<h2>Belgeler</h2>
<p class="aciklama">Tıkla, o belgenin bütün sayfaları açılır.</p>
<div class="kartlar">{''.join(kartlar)}</div>

<h2>Özet — MinerU diğer motorlara karşı</h2>
{ozet_tablo()}
<p class="aciklama">Sarı satır: taranmış belge. <b>MinerU 24.554 karakter
çıkardı; diğer dördü 0–70 karakterde kaldı.</b> Setimizde OCR'ı olan tek motor —
ve bu <b>pipeline</b> modundan geliyor, yani GPU'suz.</p>

<h2>Hız — saniye / sayfa</h2>
<p class="aciklama">Belgeler 6–100 sayfa arası olduğu için toplam süre
kıyaslanamaz; sayfa başına normalize edildi. Ham veri:
<code>out/mineru_sureler.json</code> ve <code>sonuclar.csv</code>.</p>
{hiz_tablosu()}
<p class="aciklama">MinerU hybrid satırı <b>tek sayfadan</b> ölçüldü
(resnet s.6, CPU'da zorlanmış VLM); diğerleri 9 belgenin ortalaması.
GPU'da bu sayı çok daha düşük olur — bu <b>GPU'suz üst sınır</b>.</p>

<h2>Tablo hücre doğruluğu — kriter 4 sınavı</h2>
<p class="aciklama">Aşağıdaki "gerçek" değerler uydurulmadı: resnet s.6'nın PDF
metninden birebir okundu. Test edilen soru: <i>bir sayı doğru satıra bağlanmış mı?</i></p>
<h3>resnet_2sutun_gorsel · Table 5 (topluluk sonuçları)</h3>
{uc_yonlu_tablo5()}
<div class="uyari-kutu iyi-kutu">
<b>Kesin sonuç:</b> satır birleştirme hatası <b>tamamen</b> 7,8 MB'lık ONNX
tablo modelinden geliyordu. 1,2B VLM aynı sayfada <b>Table 3, Table 4 ve
Table 5'in üçünü de %100 doğru</b> çıkardı — 26 satırın 26'sı. Kesme işareti de
düzeldi: pipeline <code>ILSVRC�14</code> basarken VLM doğru HTML varlığı basıyor.
</div>
<div class="uyari-kutu">
<b>Ama hybrid'in de kusuru var:</b> <b>başlık atamaları bir kaydı.</b>
İlk tablo (Table 3 içeriği) hiç başlık almadı, ikincisi (Table 4 içeriği)
"Table 3" başlığını aldı. Hücre değerleri kusursuz ama <b>hangi tablo olduğu
yanlış</b> — bu <b>kriter 3</b> ihlali. İlginç olan: <code>pipeline</code> bu işi
<b>doğru</b> yapıyordu.
<br><br><b>İki mod farklı yerden hata veriyor:</b>
pipeline → başlık doğru, <b>sayı yanlış</b>. hybrid → sayı doğru,
<b>başlık kaymış</b>. Kayan başlık yakınlık kuralıyla düzeltilebilir ve gözle
görülür; yanlış sayı sessizdir. <b>hybrid'in hatası daha ucuz.</b>
</div>

<h2>MinerU'nun bulduğu öğe tipleri</h2>
<p class="aciklama"><code>page_number</code> ve <code>page_footnote</code>'u ayrı
tip olarak işaretliyor — sayfa mobilyası temizliği bedava.
<code>chart</code> ile <code>image</code>'ı da ayırıyor.</p>
{oge_tipleri_tablo()}
</body></html>"""


def belge_html(stem: str, notu: str) -> str | None:
    pdf = os.path.join(CORPUS, stem + ".pdf")
    if not os.path.exists(pdf):
        print(f"  {stem}: PDF yok, atlandi")
        return None

    mn, _tipler = mineru_sayfalar(stem)
    try:
        insp = [p.markdown or ""
                for p in pdf_inspector.extract_pages_markdown(pdf).pages]
    except Exception as e:
        print(f"  {stem}: inspector sayfa API hatasi: {e}")
        insp = []

    toplam = max(len(mn), len(insp), sayfa_sayisi(stem))
    if not toplam:
        return None

    # TUM sayfalar -- secim yok
    sayfalar = list(range(1, toplam + 1))
    puan = {n: HU.anlasmazlik([insp[n - 1] if n - 1 < len(insp) else "",
                               mn[n - 1] if n - 1 < len(mn) else ""])
            for n in sayfalar}

    goruntuler = HU.render_sayfalar(pdf, stem, sayfalar)
    gorsel_n = gorselleri_kopyala(stem)
    ekler = mineru_ek_ciktilar(stem)

    ek_html = " &nbsp;·&nbsp; ".join(
        f'<a href="{y}" target="_blank">{ad}</a> '
        f'<span class="kucuk">({b // 1024} KB)</span>'
        for ad, (y, b) in ekler.items()) or '<span class="bos">yok</span>'

    esik = sorted(puan.values())[int(len(puan) * 0.8)] if puan else 1
    nav = "".join(
        f'<a href="#s{n}" class="{"yuksek" if puan[n] >= esik else ""}">{n}</a>'
        for n in sayfalar)

    bloklar = []
    for n in sayfalar:
        img = goruntuler.get(n)
        a = insp[n - 1] if n - 1 < len(insp) else ""
        b = mn[n - 1] if n - 1 < len(mn) else ""
        bloklar.append(f"""
<div class="sblok" id="s{n}">
  <div class="sbas"><span>sayfa {n} / {toplam}</span>
    <span class="puan">ayrışma {puan[n]:.3f}</span></div>
  <div class="uclu">
    <div class="kol"><div class="kbas">PDF — gerçek görünüm
      <span class="alt">hakem</span></div>
      {f'<a href="{img}" target="_blank"><img src="{img}" loading="lazy"></a>'
       if img else '<p class="bos">görüntü yok</p>'}</div>
    <div class="kol"><div class="kbas">pdf-inspector
      <span class="alt">kural tabanlı · ~0,003 sn/sayfa</span></div>
      <div class="md">{HU.render(a, False)}</div></div>
    <div class="kol mnkol"><div class="kbas">MinerU pipeline
      <span class="alt">model tabanlı · CPU</span></div>
      <div class="md">{tablo_supheleri(HU.render(b, True))}</div></div>
  </div>
</div>""")

    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{stem} — MinerU</title><style>{CSS}</style></head><body>
<div class="ust"><div class="ust-sol">{_sekmeler(False)}
<a class="geri" href="mineru.html">← MinerU indeksi</a>
<strong>{stem}</strong>
<span class="kucuk">{ihtml.escape(notu)} · {toplam} sayfanın <b>tamamı</b> ·
MinerU {gorsel_n} görsel kırptı</span></div></div>

<div class="uyari-kutu kritik" style="margin-top:12px">
<b>Bu sayfadaki MinerU çıktısı <code>backend=pipeline</code> (CPU) modundandır.</b>
Mentörünün linklediği 1,2B VLM (<code>vlm-engine</code>/<code>hybrid-engine</code>)
NVIDIA GPU istiyor ve bu makinede yok — o modun karşılaştırması
<a href="mineru.html">indeks sayfasında</a> tek sayfa için var.
</div>

<div class="ekler"><b>MinerU'nun kendi çıktıları</b>
<span class="kiyasdisi">KIYAS DIŞI — karşılaştırmada kullanılmadı</span><br>{ek_html}</div>

<div class="sayfa-nav"><b>Sayfalar:</b> {nav}
<br><span class="kucuk">Kırmızı = en çok ayrışan %20. Ayrışma puanı hiçbir
parser'ı doğru varsaymaz, sadece iki çıktının birbirinden ne kadar
ayrıştığını ölçer.</span></div>

{''.join(bloklar)}
</body></html>"""


# ======================================================================
#  ANA AKIS
# ======================================================================

def main():
    os.makedirs(MINERU_ASSETS, exist_ok=True)
    argv = sys.argv[1:]
    sadece_indeks = "--indeks" in argv
    hedef = BELGELER
    if "--only" in argv:
        ara = argv[argv.index("--only") + 1].lower()
        hedef = [(s, n) for s, n in BELGELER if ara in s.lower()]
        if not hedef:
            print(f"'{ara}' ile eslesen belge yok")
            return

    if not sadece_indeks:
        for i, (stem, notu) in enumerate(hedef, 1):
            print(f"[{i}/{len(hedef)}] {stem} ...", end=" ", flush=True)
            h = belge_html(stem, notu)
            if h is None:
                continue
            yol = os.path.join(HTML_DIR, f"mineru_{stem}.html")
            with open(yol, "w", encoding="utf-8") as f:
                f.write(h)
            print(f"{os.path.getsize(yol) / 1024:6.0f} KB", flush=True)

    yol = os.path.join(HTML_DIR, "mineru.html")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(indeks_html())
    print(f"\nINDEKS: {yol}  ({os.path.getsize(yol) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
