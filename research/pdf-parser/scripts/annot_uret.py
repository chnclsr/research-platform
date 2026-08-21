"""opendataloader.org/demo'daki ANNOT gorunumunun kendi PDF'lerimiz uzerinde uretilmesi.

NEDEN
-----
Demo sayfasinda PDF'in orijinali uzerine her ogenin turu (heading / paragraph /
table / list / image ...) sinir kutusuyla isaretli gosteriliyor. Ama demodaki
PDF'leri ONLAR secmis; kendi dosya yukleme ozellikleri "coming soon". Yani
oradan kendi belgelerimizi goremiyoruz.

Gerek de yok: ayni veri yerel CLI'dan cikiyor.
    format=["json"]  -> her oge icin  type + "page number" + "bounding box"
    format=["pdf"]   -> ONLARIN kendi cizdigi <belge>_annotated.pdf
    format=["html"]  -> ONLARIN kendi HTML'i

Bu script JSON'daki kutulari, sayfanin PNG render'i uzerine yuzde konumlu
div'ler olarak bindiriyor. Uzerine gelince ogenin metni ve turu goruluyor.

KOORDINAT -- dogrulandi, varsayilmadi
-------------------------------------
"bounding box" = [x0, y0, x1, y1], PDF noktasi, orijin SOL-ALT.
CSS icin: sol% = x0/W, ust% = (H - y1)/H.
attention sayfa 1'de 22 kutu cizilip goz ile kontrol edildi (out/bbox_kontrol.png):
kutular metin bloklarina birebir oturuyor.

HYBRID DEGIL
------------
Burada calisan sey saf Java opendataloader'dir (hybrid="off", varsayilan).
Benchmark tablosundaki "opendataloader-hybrid" AYRI bir mod: docling modelini
yerel bir sunucuda calistirip zor sayfalari ona yolluyor. Onu kurmadik.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\annot_uret.py
    .\\.venv\\Scripts\\python.exe src\\annot_uret.py --only attention
"""
from __future__ import annotations

import html as ihtml
import json
import os
import shutil
import sys

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
CORPUS_DIR = os.path.join(BASE, "corpus")
HTML_DIR = os.path.join(BASE, "html")
ASSETS_DIR = os.path.join(HTML_DIR, "assets")
ANNOT_ASSETS = os.path.join(ASSETS_DIR, "odl_annot")
ODL_OUT = os.path.join(BASE, "out", "odl_annot")

JRE_BIN = os.path.join(BASE, "tools", "jdk-21.0.12+8-jre", "bin")
if os.path.isdir(JRE_BIN):
    os.environ["PATH"] = JRE_BIN + os.pathsep + os.environ.get("PATH", "")
    os.environ["JAVA_HOME"] = os.path.dirname(JRE_BIN)

import opendataloader_pdf  # noqa: E402
import pymupdf  # noqa: E402

SAYFA_AYRAC = "<<<ODL_SAYFA>>>"
# HTML ciktisinda ayrac kacis karakterlerine cevriliyor (dogrulandi: attention'da
# 15 sayfa icin 15 kacisli ayrac var, duz haliyle 0).
AYRAC_KACIS = "&lt;&lt;&lt;ODL_SAYFA&gt;&gt;&gt;"
RENDER_DPI = 170          # html_uret.py ile ayni -- PNG'ler paylasiliyor
KISA_ESIK = 20            # bu kadar sayfaya kadar hepsi gosterilir
UZUN_TAVAN = 20           # uzun belgede azami sayfa
ANNOT_PDF_TAVAN = 12e6    # bu boyutun ustundeki annotated PDF kopyalanmaz

BELGELER = [
    "attention_tablo", "bert_2sutun_dipnot", "vgg_tablo_agirlikli",
    "resnet_2sutun_gorsel", "gpt3_uzun_75sayfa", "gpt4_uzun_gorsel",
    "sybil_tip_2sutun", "turkce_makale", "taranmis_bert_2sutun_dipnot",
]

# KONTROL GRUBU -- onlarin kendi benchmark korpusundan belgeler.
# "opendataloader kendi ornek PDF'lerinde daha iyi calisiyor" izlenimini
# ayni kodla, ayni gorunumde sinamak icin. Onlarin 200 belgesinin HEPSI
# tek sayfa; bizimkiler 6-100 sayfa akademik makale.
BENCH_PDF_DIR = os.path.join(BASE, "tools", "opendataloader-bench", "pdfs")
BENCH_ONEK = "onlarin__"


def cikti_adi(stem: str) -> str:
    """opendataloader ciktilari PDF dosya adiyla yazilir, bizim
    "onlarin__" on ekimizle degil."""
    return stem[len(BENCH_ONEK):] if stem.startswith(BENCH_ONEK) else stem


def pdf_yolunu_bul(stem: str) -> str | None:
    if stem.startswith(BENCH_ONEK):
        p = os.path.join(BENCH_PDF_DIR, stem[len(BENCH_ONEK):] + ".pdf")
    else:
        p = os.path.join(CORPUS_DIR, stem + ".pdf")
    return p if os.path.exists(p) else None

# Renk = ogenin KIMLIGI, sirasi degil. Belgeden belgeye sabit kalir.
# dataviz referans paleti (palette.md) degistirilmeden kullanildi.
TUR_RENK = {
    "heading":   "#2a78d6",
    "paragraph": "#8a94a6",
    "table":     "#eb6834",
    "list":      "#1baf7a",
    "image":     "#eda100",
    "caption":   "#a05ad6",
    "footnote":  "#d64550",
    "formula":   "#00959c",
    "text block": "#4a5568",
    "list item":  "#0f8f63",
    "table row":  "#c4501f",
    "table cell": "#f0996b",
    "header":     "#d64550",
    "footer":     "#d64550",
}
VARSAYILAN_RENK = "#6b7280"

# Bu turler acilista KAPALI gelir -- yoksa 100'lerce ic ice kutu sayfayi
# okunmaz hale getiriyor. Kullanici acabilir.
BASLANGICTA_KAPALI = {"table cell", "table row"}

# opendataloader'in ic sozlugunde 47 semantik tur var (jar icindeki
# SemanticType enum'undan okundu). Ciktiya yansiyan alt kume cok daha dar.
# Bizim 9 belgede HIC gorulmeyen ama sozlukte olanlar asagida; bu bir bulgu.
SOZLUKTE_VAR = ["footnote", "formula", "code", "block quote", "table of content",
                "title", "link", "form", "note"]


# ======================================================================
#  ODL CALISTIRMA
# ======================================================================

def odl_calistir(pdf_yol: str, stem: str) -> str:
    """4 bicimi birden uretir; zaten varsa yeniden uretmez."""
    hedef = os.path.join(ODL_OUT, stem)
    js = os.path.join(hedef, cikti_adi(stem) + ".json")
    if os.path.exists(js):
        return hedef
    os.makedirs(hedef, exist_ok=True)
    opendataloader_pdf.convert(
        input_path=pdf_yol, output_dir=hedef,
        format=["json", "markdown", "html", "pdf"],
        markdown_page_separator=SAYFA_AYRAC,
        html_page_separator=SAYFA_AYRAC,
        image_output="off", quiet=True,
    )
    return hedef


# Cocuk ogeler SADECE "kids" altinda degil. Ilk surumde bunu kacirmistim:
# listelerin ic maddeleri ve tablolarin satir/hucreleri hic cizilmiyordu,
# sadece disdaki bos kapsayici kutu goruluyordu -- "liste neden bos ve
# garip cizilmis" sorusunun cevabi buydu. Anahtarlar JSON'dan dogrulandi.
COCUK_ANAHTAR = ("kids", "list items", "rows", "cells")


def ogeleri_topla(json_yol: str) -> list[dict]:
    with open(json_yol, encoding="utf-8") as f:
        kok = json.load(f)
    ogeler: list[dict] = []

    def gez(n, derinlik=0):
        if isinstance(n, dict):
            if n.get("type") and n.get("bounding box") and n.get("page number"):
                ogeler.append({
                    "tur": str(n["type"]).lower(),
                    "sayfa": int(n["page number"]),
                    "kutu": [float(v) for v in n["bounding box"]],
                    "metin": (n.get("content") or "") if isinstance(
                        n.get("content"), str) else "",
                    "seviye": n.get("heading level"),
                    "font": n.get("font"),
                    "punto": n.get("font size"),
                    "derinlik": derinlik,
                    "atilan": False,
                })
                derinlik += 1
            for anahtar in COCUK_ANAHTAR:
                v = n.get(anahtar)
                if isinstance(v, list):
                    for c in v:
                        gez(c, derinlik)
        elif isinstance(n, list):
            for c in n:
                gez(c, derinlik)

    gez(kok)
    return ogeler


def _imza(o: dict) -> tuple:
    return (o["sayfa"], o["tur"]) + tuple(round(v, 1) for v in o["kutu"])


def atilan_ust_alt(pdf_yol: str, stem: str, varsayilan: list[dict]) -> list[dict]:
    """--include-header-footer ACIK kosuda cikan, varsayilanda OLMAYAN ogeler.

    opendataloader ust/alt bilgiyi ALGILIYOR ama varsayilan olarak ciktiya
    KOYMUYOR (include_header_footer=False). Bu yuzden "sayfanin ustundeki not
    ne kutuda ne markdown'da" gorunuyor. Burada ikinci bir kosu yapip farki
    ayri bir katman olarak gosteriyoruz -- ana olcumlerimiz DEGISMIYOR,
    onlar hala varsayilan ayarla yapiliyor.
    """
    hedef = os.path.join(ODL_OUT, stem, "ust_alt")
    js = os.path.join(hedef, cikti_adi(stem) + ".json")
    if not os.path.exists(js):
        os.makedirs(hedef, exist_ok=True)
        opendataloader_pdf.convert(
            input_path=pdf_yol, output_dir=hedef, format=["json"],
            include_header_footer=True, image_output="off", quiet=True)
    if not os.path.exists(js):
        return []
    var = {_imza(o) for o in varsayilan}
    fark = [o for o in ogeleri_topla(js) if _imza(o) not in var]
    for o in fark:
        o["atilan"] = True
    return fark


def sayfa_sec(ogeler: list[dict], toplam: int) -> list[int]:
    """Kisa belgede hepsi; uzunda YAPISI onemli olanlar.

    Uzun belgede oncelik sirasi: tablo/gorsel/liste iceren sayfalar, sonra
    baslik sayisi en yuksek olanlar. Boylece 'kutu cikarmanin zor oldugu'
    sayfalar seciliyor -- ilk N sayfa degil.
    """
    if toplam <= KISA_ESIK:
        return list(range(1, toplam + 1))

    puan: dict[int, float] = {}
    for o in ogeler:
        p = puan.setdefault(o["sayfa"], 0.0)
        agirlik = {"table": 3.0, "image": 2.0, "list": 1.5,
                   "caption": 1.0, "heading": 0.6}.get(o["tur"], 0.02)
        puan[o["sayfa"]] = p + agirlik
    sirali = sorted(puan, key=lambda n: -puan[n])[:UZUN_TAVAN - 3]
    return sorted(set(sirali) | {1, 2, toplam})


def render_sayfalar(pdf_yol: str, stem: str, sayfalar: list[int]) -> dict[int, dict]:
    """PNG uretir (html_uret.py ile ayni dosyalari paylasir) ve nokta olcusunu doner."""
    klasor = os.path.join(ASSETS_DIR, stem)
    os.makedirs(klasor, exist_ok=True)
    mat = pymupdf.Matrix(RENDER_DPI / 72.0, RENDER_DPI / 72.0)
    bilgi: dict[int, dict] = {}
    doc = pymupdf.open(pdf_yol)
    for n in sayfalar:
        if not (1 <= n <= doc.page_count):
            continue
        sayfa = doc.load_page(n - 1)
        png = os.path.join(klasor, f"p{n:03d}.png")
        if not os.path.exists(png):
            sayfa.get_pixmap(matrix=mat).save(png)
        bilgi[n] = {"src": f"assets/{stem}/p{n:03d}.png",
                    "w": sayfa.rect.width, "h": sayfa.rect.height}
    doc.close()
    return bilgi


# ======================================================================
#  HTML
# ======================================================================

def _k(s: str) -> str:
    return ihtml.escape(s or "", quote=True)


SAYFA_CSS = """
:root{
  --zemin:#f6f7f9; --kart:#fff; --cizgi:#dfe3e8;
  --murekkep:#1b1f24; --murekkep2:#5b6470; --murekkep3:#8a94a6;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --zemin:#14171c; --kart:#1c2027; --cizgi:#2c323b;
    --murekkep:#e9edf2; --murekkep2:#aab3c0; --murekkep3:#7c8695;
  }
}
:root[data-theme="dark"]{
  --zemin:#14171c; --kart:#1c2027; --cizgi:#2c323b;
  --murekkep:#e9edf2; --murekkep2:#aab3c0; --murekkep3:#7c8695;
}
*{box-sizing:border-box}
body{margin:0;background:var(--zemin);color:var(--murekkep);
  font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}
a{color:#2a78d6}
header.ust{position:sticky;top:0;z-index:40;background:var(--kart);
  border-bottom:1px solid var(--cizgi);padding:12px 20px}
header.ust h1{margin:0 0 2px;font-size:18px}
header.ust p{margin:0;color:var(--murekkep2);font-size:13px}
.kutucuklar{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:10px;
  align-items:center;font-size:13px}
.kutucuklar label{display:flex;gap:5px;align-items:center;cursor:pointer;
  padding:2px 8px;border:1px solid var(--cizgi);border-radius:20px}
.nokta{width:11px;height:11px;border-radius:3px;display:inline-block}
.sayfa{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;
  margin:18px 20px;overflow:hidden}
.sayfa > h2{margin:0;padding:9px 14px;font-size:14px;
  border-bottom:1px solid var(--cizgi);background:var(--zemin)}
.ikili{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:0}
@media(max-width:1000px){.ikili{grid-template-columns:1fr}}
.sol{padding:14px;border-right:1px solid var(--cizgi);overflow-x:auto}
.sag{padding:14px;min-width:0}
.tuval{position:relative;display:inline-block;max-width:100%}
.tuval img{display:block;width:100%;height:auto;border:1px solid var(--cizgi)}
.kutu{position:absolute;border:1.5px solid;border-radius:2px;cursor:pointer;
  transition:background .12s}
.kutu:hover,.kutu.secili{background:rgba(42,120,214,.16);border-width:2.5px}
.kutu.atilan{border-style:dashed;border-width:2px}
.kutu .etiket{position:absolute;top:-8px;left:-1px;font-size:9px;line-height:1;
  padding:2px 4px;border-radius:3px;color:#fff;white-space:nowrap;
  opacity:0;pointer-events:none}
.tuval.etiketli .kutu .etiket,.kutu:hover .etiket,.kutu.secili .etiket{opacity:1}
.sekmeler{display:flex;gap:4px;margin-bottom:10px;flex-wrap:wrap}
.sekmeler button{font:inherit;font-size:12.5px;padding:4px 11px;cursor:pointer;
  border:1px solid var(--cizgi);background:var(--zemin);color:var(--murekkep2);
  border-radius:6px}
.sekmeler button.etkin{background:#2a78d6;border-color:#2a78d6;color:#fff}
.panel{display:none}.panel.etkin{display:block}
.onizleme{width:100%;height:640px;border:1px solid var(--cizgi);border-radius:7px;
  background:#fff}
.panel pre{margin:0;white-space:pre-wrap;word-break:break-word;font-size:12.5px;
  background:var(--zemin);border:1px solid var(--cizgi);border-radius:7px;
  padding:11px;max-height:640px;overflow:auto}
.oge-kart{border:1px solid var(--cizgi);border-radius:7px;padding:12px;
  background:var(--zemin)}
.oge-kart dl{margin:0;display:grid;grid-template-columns:auto 1fr;
  gap:3px 12px;font-size:13px}
.oge-kart dt{color:var(--murekkep3)}
.oge-kart .metin{margin-top:10px;padding-top:10px;border-top:1px solid var(--cizgi);
  white-space:pre-wrap;font-size:13px}
.rozet{display:inline-block;padding:1px 8px;border-radius:20px;color:#fff;
  font-size:11.5px}
.not{margin:0 20px 18px;padding:11px 14px;background:var(--kart);
  border:1px solid var(--cizgi);border-left:3px solid #eda100;border-radius:8px;
  font-size:13px;color:var(--murekkep2)}
.sayim{color:var(--murekkep3);font-size:12px;margin:8px 0 0}
"""

# iframe icine konan sarmal. opendataloader'in HTML'i parca olarak geliyor;
# tek basina goruntulenebilmesi icin asgari bir govde gerekiyor. ICERIGE
# DOKUNULMUYOR -- sadece okunabilir yazi tipi ve tablo cizgisi veriliyor.
HTML_SARMAL = ("<!doctype html><meta charset='utf-8'>"
               "<style>body{font:14px/1.5 Georgia,serif;margin:14px;color:#111}"
               "table{border-collapse:collapse;margin:10px 0}"
               "td,th{border:1px solid #999;padding:3px 7px;font-size:13px}"
               "img{max-width:100%%;height:auto}</style>%s")

SAYFA_JS = """
document.addEventListener('click', e=>{
  const b = e.target.closest('.kutu');
  if(b){
    const s = b.closest('.sayfa');
    s.querySelectorAll('.kutu.secili').forEach(x=>x.classList.remove('secili'));
    b.classList.add('secili');
    const k = s.querySelector('.oge-kart');
    k.innerHTML = b.dataset.kart;
    s.querySelectorAll('.sekmeler button').forEach(x=>x.classList.remove('etkin'));
    s.querySelector('[data-panel="oge"]').classList.add('etkin');
    s.querySelectorAll('.panel').forEach(x=>x.classList.remove('etkin'));
    s.querySelector('.panel[data-ad="oge"]').classList.add('etkin');
    return;
  }
  const t = e.target.closest('.sekmeler button');
  if(t){
    const s = t.closest('.sayfa');
    s.querySelectorAll('.sekmeler button').forEach(x=>x.classList.remove('etkin'));
    t.classList.add('etkin');
    s.querySelectorAll('.panel').forEach(x=>x.classList.remove('etkin'));
    s.querySelector('.panel[data-ad="'+t.dataset.panel+'"]').classList.add('etkin');
  }
});
function turFiltre(){
  const acik = new Set([...document.querySelectorAll('.tur-kutu:checked')]
                       .map(x=>x.value));
  document.querySelectorAll('.kutu').forEach(b=>{
    b.style.display = acik.has(b.dataset.tur) ? '' : 'none';
  });
}
document.querySelectorAll('.tur-kutu').forEach(c=>c.addEventListener('change',turFiltre));
turFiltre();   // acilista: bazi turler kapali baslar
document.getElementById('etiket-ac').addEventListener('change', e=>{
  document.querySelectorAll('.tuval').forEach(t=>
    t.classList.toggle('etiketli', e.target.checked));
});
"""


def kutu_html(o: dict, sayfa_w: float, sayfa_h: float) -> str:
    x0, y0, x1, y1 = o["kutu"]
    sol = 100.0 * x0 / sayfa_w
    ust = 100.0 * (sayfa_h - y1) / sayfa_h      # PDF orijini SOL-ALT
    gen = 100.0 * (x1 - x0) / sayfa_w
    yuk = 100.0 * (y1 - y0) / sayfa_h
    renk = TUR_RENK.get(o["tur"], VARSAYILAN_RENK)

    satir = [f"<dt>tur</dt><dd><span class='rozet' style='background:{renk}'>"
             f"{_k(o['tur'])}</span></dd>"]
    if o.get("seviye"):
        satir.append(f"<dt>baslik seviyesi</dt><dd>{_k(str(o['seviye']))}</dd>")
    if o.get("font"):
        satir.append(f"<dt>font</dt><dd>{_k(str(o['font']))}"
                     + (f" · {o['punto']:.1f} pt" if o.get("punto") else "") + "</dd>")
    satir.append("<dt>kutu</dt><dd>[" +
                 ", ".join(f"{v:.1f}" for v in o["kutu"]) + "]</dd>")
    kart = ("<dl>" + "".join(satir) + "</dl>"
            + (f"<div class='metin'>{_k(o['metin'])}</div>" if o["metin"] else
               "<div class='metin' style='color:var(--murekkep3)'>"
               "(metin icerigi yok — gorsel/cizim)</div>"))

    ipucu = (o["metin"][:150] + ("…" if len(o["metin"]) > 150 else "")) or o["tur"]
    sinif = "kutu" + (" atilan" if o.get("atilan") else "")
    veri_tur = "__atilan__" if o.get("atilan") else o["tur"]
    etiket = (o["tur"] + " · atiliyor") if o.get("atilan") else o["tur"]
    return (f'<div class="{sinif}" data-tur="{_k(veri_tur)}" '
            f'style="left:{sol:.3f}%;top:{ust:.3f}%;width:{gen:.3f}%;'
            f'height:{yuk:.3f}%;border-color:{renk};z-index:{20 - min(o.get("derinlik", 0), 15)}" '
            f'title="{_k(etiket)} — {_k(ipucu)}" '
            f'data-kart="{_k(kart)}">'
            f'<span class="etiket" style="background:{renk}">{_k(etiket)}</span>'
            f'</div>')


def belge_html(stem: str, ogeler: list[dict], sayfalar: list[int],
               bilgi: dict[int, dict], toplam: int, md_sayfa: dict[int, str],
               html_sayfa: dict[int, str],
               annot_pdf: str | None, odl_html: str | None) -> str:
    normal = [o for o in ogeler if not o.get("atilan")]
    atilan = [o for o in ogeler if o.get("atilan")]
    turler = sorted({o["tur"] for o in normal})
    kutucuk = "".join(
        f'<label><input type="checkbox" class="tur-kutu" value="{_k(t)}"'
        f'{"" if t in BASLANGICTA_KAPALI else " checked"}>'
        f'<span class="nokta" style="background:{TUR_RENK.get(t, VARSAYILAN_RENK)}">'
        f'</span>{_k(t)} <span style="color:var(--murekkep3)">'
        f'({sum(1 for o in normal if o["tur"] == t)})</span></label>'
        for t in turler)
    if atilan:
        kutucuk += (
            '<label style="border-color:#d64550"><input type="checkbox" '
            'class="tur-kutu" value="__atilan__">'
            '<span class="nokta" style="background:#d64550"></span>'
            f'ust/alt bilgi — <b>varsayilanda atiliyor</b> '
            f'<span style="color:var(--murekkep3)">({len(atilan)})</span></label>')
    eksik = ", ".join(SOZLUKTE_VAR)

    baglanti = []
    if annot_pdf:
        baglanti.append(f'<a href="{annot_pdf}" target="_blank">'
                        'opendataloader\'in kendi cizdigi annotated PDF</a>')
    if odl_html:
        baglanti.append(f'<a href="{odl_html}" target="_blank">'
                        'opendataloader\'in kendi HTML\'i</a>')
    baglanti.append('<a href="index.html">← ana sayfa</a>')
    baglanti.append('<a href="mineru.html">MinerU</a>')
    baglanti.append('<a href="annot_index.html">etiketli gorunum dizini</a>')
    if not stem.startswith(BENCH_ONEK):
        baglanti.append(f'<a href="{stem}.html">yan yana karsilastirma</a>')

    bloklar = []
    for n in sayfalar:
        b = bilgi.get(n)
        if not b:
            continue
        sayfa_ogeleri = [o for o in ogeler if o["sayfa"] == n]
        kutular = "".join(kutu_html(o, b["w"], b["h"]) for o in sayfa_ogeleri)
        sayim = {}
        for o in sayfa_ogeleri:
            sayim[o["tur"]] = sayim.get(o["tur"], 0) + 1
        ozet = " · ".join(f"{k}: {v}" for k, v in sorted(sayim.items())) or "oge yok"

        json_metin = json.dumps(
            [{"type": o["tur"], "bounding box": o["kutu"],
              "content": o["metin"][:400]} for o in sayfa_ogeleri],
            ensure_ascii=False, indent=1)

        ham_html = html_sayfa.get(n, "")
        if ham_html:
            # sandbox: betik calismaz, kendi sayfamiza karisamaz
            onizleme = (f'<iframe class="onizleme" sandbox loading="lazy" '
                        f'srcdoc="{_k(HTML_SARMAL % ham_html)}"></iframe>')
            kaynak = f"<pre>{_k(ham_html)}</pre>"
        else:
            onizleme = kaynak = ('<pre style="color:var(--murekkep3)">'
                                 '(bu sayfa icin HTML ayraci bulunamadi)</pre>')

        bloklar.append(f"""
<section class="sayfa">
  <h2>Sayfa {n} / {toplam} <span style="color:var(--murekkep3);font-weight:400">
      — {_k(ozet)}</span></h2>
  <div class="ikili">
    <div class="sol">
      <div class="tuval"><img src="{b['src']}" alt="sayfa {n}" loading="lazy">
        {kutular}</div>
      <p class="sayim">Kutuya tikla → sagda o ogenin ayrintisi. Kutular
         opendataloader'in JSON ciktisindan geliyor, benim tahminim degil.</p>
    </div>
    <div class="sag">
      <div class="sekmeler">
        <button data-panel="oge" class="etkin">Secili oge</button>
        <button data-panel="md">MD</button>
        <button data-panel="html">HTML (islenmis)</button>
        <button data-panel="htmlkaynak">HTML (kaynak)</button>
        <button data-panel="json">JSON</button>
      </div>
      <div class="panel etkin" data-ad="oge">
        <div class="oge-kart"><span style="color:var(--murekkep3)">
          Soldan bir kutu sec.</span></div>
      </div>
      <div class="panel" data-ad="md"><pre>{_k(md_sayfa.get(n, '(bu sayfa icin markdown ayraci bulunamadi)'))}</pre></div>
      <div class="panel" data-ad="html">{onizleme}</div>
      <div class="panel" data-ad="htmlkaynak">{kaynak}</div>
      <div class="panel" data-ad="json"><pre>{_k(json_metin)}</pre></div>
    </div>
  </div>
</section>""")

    secim_not = ("Belgenin tamami gosteriliyor."
                 if toplam <= KISA_ESIK else
                 f"{toplam} sayfadan {len(sayfalar)} tanesi gosteriliyor: "
                 "tablo / gorsel / liste iceren sayfalar oncelikli secildi "
                 "(ilk N sayfa degil), + ilk iki ve son sayfa.")

    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_k(stem)} — opendataloader etiketli gorunum</title>
<style>{SAYFA_CSS}</style></head><body>
<header class="ust">
  <h1>{_k(stem)} — opendataloader etiketli gorunum</h1>
  <p>opendataloader.org/demo'daki <b>annot</b> gorunumunun aynisi, kendi PDF'imiz
     uzerinde. Kutular ve turler <b>opendataloader'in JSON ciktisindan</b>
     ({len(normal)} oge) alindi; hicbiri benim tahminim degil. Calisan mod:
     <b>saf Java opendataloader</b> (hybrid kapali).</p>
  <p style="font-size:12.5px;color:var(--murekkep3);margin-top:4px">
     opendataloader'in ic sozlugunde 47 semantik tur var (jar'daki SemanticType
     enum'undan okundu). Bu belgede sadece {len(turler)} tanesi cikti.
     Ciktiya hic yansimayanlar arasinda: {_k(eksik)}.</p>
  <p style="margin-top:6px">{" &nbsp;·&nbsp; ".join(baglanti)}</p>
  <div class="kutucuklar">{kutucuk}
    <label style="border-style:dashed"><input type="checkbox" id="etiket-ac">
      tur etiketlerini goster</label>
  </div>
</header>
<p class="not">{_k(secim_not)} Kutu koordinati PDF noktasi cinsinden
   (orijin sol-alt); yuzdeye cevrilerek goruntuye bindirildi. Cizim
   attention sayfa 1'de goz ile dogrulandi.</p>
{"".join(bloklar)}
<script>{SAYFA_JS}</script></body></html>"""


def dizin_html(kayitlar: list[tuple]) -> str:
    def blok(kume, baslik, aciklama):
        if not kume:
            return ""
        s = (f'<tr><td colspan="5" style="background:var(--zemin);'
             f'font-weight:600;font-size:12.5px">{_k(baslik)}'
             f'<span style="font-weight:400;color:var(--murekkep3)"> — '
             f'{_k(aciklama)}</span></td></tr>')
        return s + "".join(
            f'<tr><td><a href="annot_{a}.html">'
            f'{_k(a.replace(BENCH_ONEK, ""))}</a></td>'
            f'<td style="text-align:right">{t}</td>'
            f'<td style="text-align:right">{g}</td>'
            f'<td style="text-align:right">{o}</td>'
            f'<td>{_k(ozet)}</td></tr>'
            for a, t, g, o, ozet in kume)

    bizim = [k for k in kayitlar if not k[0].startswith(BENCH_ONEK)]
    onlarin = [k for k in kayitlar if k[0].startswith(BENCH_ONEK)]
    satir = (blok(bizim, "BIZIM KORPUS",
                  "6-100 sayfa akademik makale, 2 sutun, tablo, dipnot")
             + blok(onlarin, "KONTROL GRUBU — ONLARIN KORPUSU",
                    "opendataloader-bench'ten, hepsi TEK sayfa; ayni kod, "
                    "ayni gorunum"))
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Etiketli gorunum — dizin</title><style>{SAYFA_CSS}
table{{border-collapse:collapse;width:calc(100% - 40px);margin:18px 20px;
  background:var(--kart);border:1px solid var(--cizgi);border-radius:8px;
  overflow:hidden;font-size:14px}}
th,td{{padding:8px 12px;border-bottom:1px solid var(--cizgi);text-align:left}}
th{{background:var(--zemin);font-size:12.5px;color:var(--murekkep2)}}
</style></head><body>
<header class="ust"><h1>opendataloader — etiketli (annot) gorunum</h1>
<p>Her belgede PDF'in orijinali uzerine, opendataloader'in tanidigi ogelerin
   sinir kutulari bindirildi. Kaynak: opendataloader JSON ciktisi.</p>
<p style="margin-top:6px"><a href="index.html">← ana sayfa</a> &nbsp;·&nbsp;
   <a href="olcumler.html">Ölçümler</a> &nbsp;·&nbsp;
   <a href="mineru.html">MinerU</a></p></header>
<table><thead><tr><th>belge</th><th>sayfa</th><th>gosterilen</th>
<th>oge</th><th>tur dagilimi</th></tr></thead><tbody>{satir}</tbody></table>
<p class="not">Calisan mod saf Java opendataloader'dir (hybrid kapali).
   Benchmark tablosundaki "opendataloader-hybrid" ayri bir moddur: zor sayfalari
   yerel bir docling sunucusuna yollar, kurulmadi.</p>
</body></html>"""


# ======================================================================

def main() -> None:
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].lower()

    kac_bench = 3
    if "--bench" in sys.argv:
        kac_bench = int(sys.argv[sys.argv.index("--bench") + 1])

    os.makedirs(ANNOT_ASSETS, exist_ok=True)
    os.makedirs(ODL_OUT, exist_ok=True)
    kayitlar = []

    liste = list(BELGELER)
    if kac_bench and os.path.isdir(BENCH_PDF_DIR):
        bench = sorted(f[:-4] for f in os.listdir(BENCH_PDF_DIR)
                       if f.lower().endswith(".pdf"))[:kac_bench]
        liste += [BENCH_ONEK + b for b in bench]

    for stem in liste:
        if only and only not in stem.lower():
            continue
        pdf_yol = pdf_yolunu_bul(stem)
        if not pdf_yol:
            print(f"  ATLANDI (PDF yok): {stem}")
            continue

        print(f"\n=== {stem} ===", flush=True)
        print("  opendataloader (json+md+html+pdf)...", end=" ", flush=True)
        klasor = odl_calistir(pdf_yol, stem)
        print("bitti")

        js = os.path.join(klasor, cikti_adi(stem) + ".json")
        if not os.path.exists(js):
            print("  JSON uretilemedi, atlandi")
            continue
        ogeler = ogeleri_topla(js)          # varsayilan ayar = OLCTUGUMUZ cikti
        print("  ust/alt bilgi farki icin ikinci kosu...", end=" ", flush=True)
        atilanlar = atilan_ust_alt(pdf_yol, stem, ogeler)
        print(f"{len(atilanlar)} atilan oge")

        doc = pymupdf.open(pdf_yol)
        toplam = doc.page_count
        doc.close()

        # sayfa secimi SADECE varsayilan ciktiya bakar -- atilan katman
        # gorunum icin, olcum icin degil
        sayfalar = sayfa_sec(ogeler, toplam)
        bilgi = render_sayfalar(pdf_yol, stem, sayfalar)

        # ONLARIN markdown'i, sayfa ayracina gore bolunmus
        md_sayfa: dict[int, str] = {}
        md_yol = os.path.join(klasor, cikti_adi(stem) + ".md")
        if os.path.exists(md_yol):
            with open(md_yol, encoding="utf-8") as f:
                parcalar = f.read().split(SAYFA_AYRAC)[1:]
            for i, p in enumerate(parcalar, 1):
                md_sayfa[i] = p.strip()

        # ONLARIN HTML'i, ayni ayraca gore bolunmus (HTML'de kacisli geliyor)
        html_sayfa: dict[int, str] = {}
        html_kaynak_yol = os.path.join(klasor, cikti_adi(stem) + ".html")
        if os.path.exists(html_kaynak_yol):
            with open(html_kaynak_yol, encoding="utf-8") as f:
                govde = f.read()
            parcalar = govde.split(AYRAC_KACIS)[1:]
            for i, p in enumerate(parcalar, 1):
                p = p.replace("</body>", "").replace("</html>", "").strip()
                html_sayfa[i] = p

        # ONLARIN kendi cizimleri
        annot_kaynak = os.path.join(klasor, cikti_adi(stem) + "_annotated.pdf")
        annot_rel = None
        if os.path.exists(annot_kaynak):
            if os.path.getsize(annot_kaynak) <= ANNOT_PDF_TAVAN:
                shutil.copy2(annot_kaynak,
                             os.path.join(ANNOT_ASSETS, stem + "_annotated.pdf"))
                annot_rel = f"assets/odl_annot/{stem}_annotated.pdf"
            else:
                print(f"  not: annotated PDF {os.path.getsize(annot_kaynak)/1e6:.1f} MB"
                      " — kopyalanmadi")
        html_rel = None
        if os.path.exists(html_kaynak_yol):
            shutil.copy2(html_kaynak_yol,
                         os.path.join(ANNOT_ASSETS, stem + "_odl.html"))
            html_rel = f"assets/odl_annot/{stem}_odl.html"

        with open(os.path.join(HTML_DIR, f"annot_{stem}.html"), "w",
                  encoding="utf-8") as f:
            f.write(belge_html(stem, ogeler + atilanlar, sayfalar, bilgi, toplam,
                               md_sayfa, html_sayfa, annot_rel, html_rel))

        sayim: dict[str, int] = {}
        for o in ogeler:
            sayim[o["tur"]] = sayim.get(o["tur"], 0) + 1
        ozet = " · ".join(f"{k} {v}" for k, v in
                          sorted(sayim.items(), key=lambda x: -x[1]))
        kayitlar.append((stem, toplam, len(sayfalar), len(ogeler), ozet))
        print(f"  {len(ogeler)} oge, {len(sayfalar)}/{toplam} sayfa · {ozet}")

    if kayitlar:
        with open(os.path.join(HTML_DIR, "annot_index.html"), "w",
                  encoding="utf-8") as f:
            f.write(dizin_html(kayitlar))
        print("\nHazir: html/annot_index.html")


if __name__ == "__main__":
    main()
