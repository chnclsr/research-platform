"""Yan yana gorsel karsilastirma arayuzu uretir.

Her sayfa icin dort sutun:

    GERCEK SAYFA  |  pypdf  |  opendataloader  |  pdf-inspector
    (PDF -> PNG)

Amac: "hangisi sayfayi daha dogru basmis" sorusunu GOZLE cevaplayabilmek.
Solda gercek sayfanin goruntusu sart -- dogrusu gorunmeden hangi ciktinin
dogru oldugu soylenemez.


ADALET KURALI
-------------
Uc parser'in ciktisi da AYNI donusturucuden gecer: `markdown` kutuphanesi,
ayni eklentiler, ayni ayarlar. Hicbir parser'a ozel guzellestirme yapilmaz.

  * opendataloader'in KENDI HTML ciktisi da var ve daha guzel gorunuyor.
    Karsilastirma sutununda KULLANILMIYOR -- kullanilsaydi digerlerine
    haksizlik olurdu. Ayri bir baglanti olarak, "kiyas disi" etiketiyle
    veriliyor.
  * pypdf duz metin uretir, Markdown degil. Ayni donusturucuden gecirilir
    ve sonuc duz paragraf olur. Bu bir dezavantaj degil, gercegin kendisi:
    pypdf yapi uretmiyor.
  * Gorseller: sadece opendataloader gorsel referansi uretiyor. Digerlerinde
    gorunmemesi donusturucu kusuru degil, parser'in yetenegi.


IKI GORUNUM
-----------
    BELGE : Markdown islenmis, gorseller basili -- "arXiv HTML gibi"
    HAM   : parser'in urettigi ham metin (monospace)

HAM gorunum SART. Bozuk bir Markdown tablosu islenince "duzgun" gorunur ve
sutun hizasi bozuklugu KAYBOLUR -- yani tam olarak olcmek istedigimiz kusur
gizlenir. Gercek bozulma ham metinde gorunur.


SAYFA SECIMI
------------
Elle "sorunlu sayfa" secmek TARAFLI olur: sorunlu sayfalar pypdf ve
inspector incelenerek bulunmustu, dolayisiyla sadece o iki parser'in
kusurlarini gosterir. Bir parser'a OZGU, hic bakmadigimiz sayfadaki
kusurlar gorunmez kalir.

Bu yuzden:
  * <= KISA_ESIK sayfalik belgeler: TUM SAYFALAR (7 belge, secim yok)
  * uzun belgeler (gpt3 75, gpt4 100): otomatik ANLASMAZLIK PUANI ile
    siralanir; en cok ayrisan sayfalar + kontrol ornegi alinir.
    Puan hicbir parser'i "dogru" varsaymaz, sadece ayrismayi olcer.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\html_uret.py
    .\\.venv\\Scripts\\python.exe src\\html_uret.py --only sybil
    .\\.venv\\Scripts\\python.exe src\\html_uret.py --hepsi     # uzunlar dahil tum sayfalar

Cikti
-----
    html/index.html          belge secici
    html/<belge>.html        sayfa sayfa karsilastirma
    html/assets/<belge>/     sayfa goruntuleri (PNG)
    html/assets/odl/<belge>/ opendataloader'in cikardigi gorseller + kendi HTML'i
"""
from __future__ import annotations

import html as html_mod
import json
import os
import re
import shutil
import sys

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
CORPUS_DIR = os.path.join(BASE, "corpus")
HTML_DIR = os.path.join(BASE, "html")
ASSETS_DIR = os.path.join(HTML_DIR, "assets")
ODL_ASSETS = os.path.join(ASSETS_DIR, "odl")

JRE_BIN = os.path.join(BASE, "tools", "jdk-21.0.12+8-jre", "bin")
if os.path.isdir(JRE_BIN):
    os.environ["PATH"] = JRE_BIN + os.pathsep + os.environ.get("PATH", "")
    os.environ["JAVA_HOME"] = os.path.dirname(JRE_BIN)

import markdown as md_lib  # noqa: E402
import opendataloader_pdf  # noqa: E402
import pdf_inspector  # noqa: E402
import pymupdf  # noqa: E402
import pymupdf4llm  # noqa: E402
import pypdf  # noqa: E402

ODL_SEP = "<<<ODL_PAGE>>>"
RENDER_DPI = 100      # 170'ten dusuruldu: 1129 PNG 130 MB tutuyordu, GitHub icin
                      # fazla. 100 DPI'da ~35 MB. Bedeli: buyutec biraz yumusak.
KISA_ESIK = 20        # bu kadar veya daha az sayfaliysa tamami basilir
UZUN_TOP_N = 18       # uzun belgede en cok ayrisan kac sayfa
UZUN_KONTROL = 6      # + kac kontrol sayfasi (dusuk ayrisma -- karsi ornek)
GORSEL_TAVAN = 24     # tek sayfada gosterilecek azami gorsel

BELGELER = [
    "turkce_makale", "sybil_tip_2sutun", "bert_2sutun_dipnot",
    "vgg_tablo_agirlikli", "resnet_2sutun_gorsel", "attention_tablo",
    "gpt3_uzun_75sayfa", "gpt4_uzun_gorsel", "taranmis_bert_2sutun_dipnot",
]


# ======================================================================
#  PARSERLAR -- sayfa bazli cikti
# ======================================================================

def pypdf_pages(path: str) -> list[str]:
    """Sistemde su an kullanilan yol (acquisition.py ile ayni)."""
    reader = pypdf.PdfReader(path)
    return [p.extract_text() or "" for p in reader.pages]


def inspector_pages(path: str) -> list[str]:
    """DIKKAT: extract_pages_markdown(), process_pdf().markdown DEGIL.

    Olcumlerin tamami process_pdf().markdown ile yapildi. Iki API biraz
    farkli cikti verir (bert'te 42 vs 44 baslik, bulgular.md 2.5). Sayfa
    bazli gorunum icin sayfa API'si sart; bu fark HTML'de uyari olarak yazili.
    """
    res = pdf_inspector.extract_pages_markdown(path)
    return [p.markdown or "" for p in res.pages]


def p4llm_pages(path: str) -> list[str]:
    """pymupdf4llm, sayfa bazli. Adi yaniltici: LLM CALISTIRMIYOR."""
    parcalar = pymupdf4llm.to_markdown(path, page_chunks=True, show_progress=False)
    return [(p.get("text") or "") for p in parcalar]


def odl_pages(path: str, stem: str) -> tuple[list[str], str | None, int]:
    """opendataloader: (sayfalar, kendi HTML dosyasinin yolu, gorsel sayisi).

    Cikti KALICI bir klasore yazilir -- gorseller HTML'den referans
    edilecegi icin gecici klasor kullanilamaz.
    """
    hedef = os.path.join(ODL_ASSETS, stem)
    shutil.rmtree(hedef, ignore_errors=True)
    os.makedirs(hedef, exist_ok=True)

    opendataloader_pdf.convert(
        input_path=path, output_dir=hedef, format=["markdown", "html"],
        markdown_page_separator=ODL_SEP, quiet=True,
    )

    md, kendi_html = "", None
    for root, _d, files in os.walk(hedef):
        for fn in files:
            p = os.path.join(root, fn)
            if fn.lower().endswith(".md"):
                with open(p, encoding="utf-8") as f:
                    md = f.read()
            elif fn.lower().endswith(".html"):
                kendi_html = os.path.relpath(p, HTML_DIR).replace("\\", "/")

    gorsel = sum(1 for r, _d, fs in os.walk(hedef) for f in fs
                 if f.lower().endswith((".png", ".jpg", ".jpeg")))

    # Gorsel yollarini html/ klasorune gore duzelt.
    # Kaynak bicim: ![](<belge_images/imageFile2.png>)
    onek = f"assets/odl/{stem}/"
    md = re.sub(r"!\[([^\]]*)\]\(<?([^)>]+)>?\)",
                lambda m: f"![{m.group(1)}]({onek}{m.group(2)})", md)

    parts = md.split(ODL_SEP)
    sayfalar = parts[1:] if len(parts) > 1 else ([md] if md else [])
    return sayfalar, kendi_html, gorsel


def mineru_pages(stem: str) -> list[str]:
    """MinerU sayfalarini HAZIR ciktidan okur -- yeniden ayristirmaz.

    MinerU ayri ortamda (.venv-mineru) kosuyor; buradan cagrilamaz. Ama
    mineru_kos.py ciktisini diske yazdi: out/mineru_json/<belge>_content_list.json
    Her ogenin page_idx'i var -> sayfa hizalamasi KESIN.

    DIKKAT: bu backend=pipeline (CPU) ciktisidir, MinerU'nun TAVANI DEGIL.
    Sutun basliginda bu etiket duruyor.
    """
    yol = os.path.join(BASE, "out", "mineru_json", f"{stem}_content_list.json")
    if not os.path.exists(yol):
        return []
    with open(yol, encoding="utf-8") as f:
        ogeler = json.load(f)
    if not ogeler:
        return []

    kovalar: list[list[str]] = [[] for _ in
                                range(max(o.get("page_idx", 0) for o in ogeler) + 1)]
    for og in ogeler:
        t = og.get("type")
        if t in ("text", "aside_text", "footer", "page_footnote", "page_number"):
            metin = (og.get("text") or "").strip()
            if not metin:
                continue
            sev = og.get("text_level")
            parca = f"{'#' * int(sev)} {metin}" if sev else metin
        elif t == "table":
            bas = " ".join(og.get("table_caption") or [])
            parca = (f"**{bas}**\n\n" if bas else "") + (og.get("table_body") or "")
        elif t in ("image", "chart"):
            parca = " ".join(og.get("image_caption") or og.get("chart_caption") or [])
        elif t == "list":
            parca = "\n".join(f"- {x}" for x in (og.get("list_items") or []))
        else:
            parca = (og.get("text") or "").strip()
        if parca:
            kovalar[og.get("page_idx", 0)].append(parca)
    return ["\n\n".join(k) for k in kovalar]


# ======================================================================
#  ANLASMAZLIK PUANI  (sayfa secimi icin -- elle secim yerine)
# ======================================================================

def _kelimeler(s: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]{4,}", s)}


def anlasmazlik(sayfa_metinleri: list[str]) -> float:
    """Uc parser bu sayfada ne kadar ayrisiyor? 0 = ayni, 1 = tamamen farkli.

    HICBIR parser'i 'dogru' varsaymaz -- sadece ayrismayi olcer. Boylece
    hangi parser'in kusurlu oldugunu bilmeden aday sayfa bulunabilir.
    """
    # Not: bu puan DORT parser'in ciktisini birden karsilastirir. Agirliklar
    # (0.5 / 0.3 / 0.2) elle secilmis bir sezgiseldir, turetilmis degil --
    # amaci "buraya bak" demek, kusur MIKTARINI olcmek degil.
    kumeler = [_kelimeler(s) for s in sayfa_metinleri]
    dolu = [k for k in kumeler if k]
    if len(dolu) < 2:
        return 1.0 if any(kumeler) else 0.0

    birlesim = set().union(*dolu)
    kesisim = set.intersection(*dolu)
    kelime_farki = 1 - (len(kesisim) / len(birlesim)) if birlesim else 0.0

    # yapi farki: baslik ve tablo satiri sayilarinin yayilimi
    def yapi(s):
        return (len(re.findall(r"(?m)^#{1,6}\s", s)),
                len(re.findall(r"(?m)^\s*\|", s)))

    yapilar = [yapi(s) for s in sayfa_metinleri]
    yapi_farki = 0.0
    for i in range(2):
        d = [y[i] for y in yapilar]
        if max(d) > 0:
            yapi_farki += (max(d) - min(d)) / max(d)
    yapi_farki /= 2

    # uzunluk yayilimi
    boylar = [len(s) for s in sayfa_metinleri]
    boy_farki = ((max(boylar) - min(boylar)) / max(boylar)) if max(boylar) else 0.0

    return round(0.5 * kelime_farki + 0.3 * yapi_farki + 0.2 * boy_farki, 4)


def sayfa_sec(ciktilar: dict[str, list[str]], toplam: int,
              hepsi: bool) -> tuple[list[int], dict[int, float], str]:
    puanlar = {}
    for n in range(1, toplam + 1):
        metinler = [(ciktilar[k][n - 1] if n - 1 < len(ciktilar[k]) else "")
                    for k in ("pypdf", "insp", "odl", "p4llm", "mineru") if k in ciktilar]
        puanlar[n] = anlasmazlik(metinler)

    if hepsi or toplam <= KISA_ESIK:
        return list(range(1, toplam + 1)), puanlar, "tum sayfalar"

    sirali = sorted(puanlar, key=lambda n: -puanlar[n])
    ust = sirali[:UZUN_TOP_N]
    alt = sirali[-UZUN_KONTROL:]          # kontrol: en az ayrisan sayfalar
    secim = sorted(set(ust) | set(alt))
    return secim, puanlar, (f"{len(secim)}/{toplam} sayfa — en cok ayrisan "
                            f"{UZUN_TOP_N} + kontrol icin en az ayrisan {UZUN_KONTROL}")


# ======================================================================
#  MARKDOWN -> HTML   (UCUNE DE AYNI SEKILDE UYGULANIR)
# ======================================================================

_MD = md_lib.Markdown(extensions=["tables", "sane_lists"], output_format="html")


def render(metin: str, gorsel_goster: bool) -> str:
    if not metin.strip():
        return '<p class="bos">(bu sayfa icin cikti yok)</p>'

    _MD.reset()
    h = _MD.convert(metin)

    # Cok sayida sahte gorsel referansi olan sayfalar (vgg'de 698 tane var)
    # tarayiciyi kilitler. Tavan uygulanir, kalani sayiyla bildirilir.
    if gorsel_goster:
        imgler = re.findall(r"<img[^>]*>", h)
        if len(imgler) > GORSEL_TAVAN:
            for im in imgler[GORSEL_TAVAN:]:
                h = h.replace(im, "", 1)
            h = (f'<div class="tbl-uyari">bu sayfada {len(imgler)} gorsel '
                 f'referansi var; ilk {GORSEL_TAVAN} tanesi gosteriliyor</div>' + h)
    else:
        h = re.sub(r"<img[^>]*>", "", h)

    # Sutun sayisi tutarsiz tablolari isaretle -- olcutun 4. maddesi bu.
    h = _tablo_uyari(h)
    return h


def _tablo_uyari(h: str) -> str:
    def isle(m):
        blok = m.group(0)
        satir_hucre = [len(re.findall(r"<t[dh][ >]", tr))
                       for tr in re.findall(r"<tr>.*?</tr>", blok, re.S)]
        if len(set(satir_hucre)) > 1:
            return (f'<div class="tbl-uyari">sutun sayisi tutarsiz: '
                    f'{sorted(set(satir_hucre))}</div>{blok}')
        return blok

    return re.sub(r"<table>.*?</table>", isle, h, flags=re.S)


# ======================================================================
#  SAYFA GORUNTULERI
# ======================================================================

def render_sayfalar(pdf_path: str, stem: str, sayfalar: list[int]) -> dict[int, str]:
    hedef = os.path.join(ASSETS_DIR, stem)
    os.makedirs(hedef, exist_ok=True)
    mat = pymupdf.Matrix(RENDER_DPI / 72.0, RENDER_DPI / 72.0)
    yollar = {}
    doc = pymupdf.open(pdf_path)
    for n in sayfalar:
        if 1 <= n <= doc.page_count:
            png = os.path.join(hedef, f"p{n:03d}.png")
            if not os.path.exists(png):
                doc.load_page(n - 1).get_pixmap(matrix=mat).save(png)
            yollar[n] = f"assets/{stem}/p{n:03d}.png"
    doc.close()
    return yollar


# ======================================================================
#  HTML URETIMI
# ======================================================================

PARSER_BILGI = [
    ("pypdf", "pypdf", "Sistemde su an kullanilan", False),
    ("insp", "pdf-inspector", "Aday — Rust", False),
    ("odl", "opendataloader", "Aday — Java", True),
    ("p4llm", "pymupdf4llm", "Aday — PyMuPDF (LLM DEGIL)", False),
    ("mineru", "MinerU", "Aday — pipeline · CPU (tavani degil)", False),
]


def belge_html(stem: str, sayfalar: list[int], goruntuler: dict[int, str],
               ciktilar: dict[str, list[str]], toplam: int, puanlar: dict[int, float],
               secim_aciklama: str, odl_html: str | None, odl_gorsel: int) -> str:
    bloklar = []
    for n in sayfalar:
        sutunlar = []
        img = goruntuler.get(n)
        sutunlar.append(
            f'<section class="sut sut-pdf" data-parser="pdf"><header><h3>GERCEK SAYFA</h3>'
            f'<span class="alt">PDF goruntusu — hakem · <b>tikla, buyut</b></span></header>'
            f'<div class="icerik">'
            + (f'<img class="buyutulebilir" src="{img}" alt="sayfa {n}" '
               f'loading="lazy" title="Buyutmek icin tikla">' if img
               else '<p class="bos">(goruntu yok)</p>')
            + '</div></section>'
        )

        for kisa, ad, aciklama, gorselli in PARSER_BILGI:
            liste = ciktilar.get(kisa, [])
            metin = liste[n - 1] if 0 <= n - 1 < len(liste) else ""
            sutunlar.append(
                f'<section class="sut" data-parser="{kisa}">'
                f'<header><h3>{ad}</h3>'
                f'<span class="alt">{aciklama} · {len(metin):,} krk</span></header>'
                f'<div class="icerik">'
                f'<div class="v-belge">{render(metin, gorselli)}</div>'
                f'<pre class="v-ham">{html_mod.escape(metin) or "(cikti yok)"}</pre>'
                f'</div></section>'
            )

        p = puanlar.get(n, 0.0)
        renk = "yuksek" if p > 0.45 else ("orta" if p > 0.25 else "dusuk")
        bloklar.append(
            f'<article class="sayfa" id="s{n}">'
            f'<div class="sayfa-baslik">Sayfa {n}'
            f'<span class="puan {renk}">anlasmazlik {p:.2f}</span></div>'
            f'<div class="izgara">{"".join(sutunlar)}</div></article>'
        )

    nav = "".join(
        f'<a href="#s{n}" class="{"yuksek" if puanlar.get(n,0) > 0.45 else ""}">{n}</a>'
        for n in sayfalar
    )
    odl_bag = (f'<p><a href="{odl_html}" target="_blank">'
               f'opendataloader&rsquo;in KENDI HTML ciktisi &rarr;</a> '
               f'<em>kiyas disi — digerlerinde karsiligi yok, bu yuzden '
               f'karsilastirma sutununda kullanilmiyor.</em></p>'
               if odl_html else "")

    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{stem} — parser karsilastirmasi</title>
<style>{CSS}</style></head><body>
<div class="ust">
  <div class="ust-sol">
    <nav class="sekmeler"><a href="index.html">Belgeler</a><a href="annot_index.html">Etiketli gorunum</a><a href="olcumler.html">Olcumler</a><a href="mineru.html">MinerU</a></nav>
    <strong>{stem}</strong><span class="kucuk">{secim_aciklama}</span></div>
  <div class="ust-sag"><div class="segment">
    <button id="btn-belge" class="aktif">Belge</button>
    <button id="btn-ham">Ham metin</button></div></div>
</div>
<div class="sutun-secim">Sutunlar:
  <label><input type="checkbox" data-sut="pdf" checked> gercek sayfa</label>
  <label><input type="checkbox" data-sut="pypdf" checked> pypdf</label>
  <label><input type="checkbox" data-sut="insp" checked> pdf-inspector</label>
  <label><input type="checkbox" data-sut="odl" checked> opendataloader</label>
  <label><input type="checkbox" data-sut="p4llm" checked> pymupdf4llm</label>
  <label><input type="checkbox" data-sut="mineru" checked> MinerU</label>
  <span class="genislik-ayar">| sütun genişliği
    <input type="range" id="sut-genislik" min="240" max="700" step="20" value="360">
    <b id="sut-genislik-d">360px</b></span>
  <span class="kucuk">— sürükleyerek veya alttaki çubukla sağa/sola kaydır</span>
</div>
<div class="sayfa-nav">Sayfaya git: {nav}</div>
<div class="uyari-kutu">
  <strong>Okurken dikkat:</strong>
  <ul>
    <li><b>Ham metin</b> asil olcum gorunumudur. Bozuk bir Markdown tablosu
        Belge gorunumunde duzgun gorunur; hizasizlik ancak ham metinde cikar.</li>
    <li><b>Adalet:</b> uc sutun da ayni <code>markdown</code> kutuphanesinden,
        ayni ayarlarla gecer. Hicbirine ozel guzellestirme yok.</li>
    <li><b>Gorseller:</b> yalnizca opendataloader gorsel referansi uretiyor
        ({odl_gorsel} dosya). Digerlerinde gorsel olmamasi donusturucu kusuru
        degil, parser'in yetenegidir. Vektor cizim olarak gomulu sekilleri
        (resnet: 1.364 nesne) <b>hicbir arac</b> cikaramaz.</li>
    <li>pdf-inspector sutunu <code>extract_pages_markdown()</code> ciktisidir;
        olcumler <code>process_pdf().markdown</code> ile yapildi (bulgular.md &sect;2.5).</li>
    <li><b>anlasmazlik</b> puani: uc parser bu sayfada ne kadar ayrisiyor.
        Hicbirini dogru varsaymaz; yuksek puan "buraya bak" demektir.</li>
  </ul>
  {odl_bag}
</div>
{"".join(bloklar)}

<div id="buyutec" class="buyutec">
  <div class="bt-cubuk">
    <span id="bt-baslik"></span>
    <button data-z="-">&minus;</button>
    <span id="bt-oran">100%</span>
    <button data-z="+">+</button>
    <button data-z="sigdir">Sigdir</button>
    <button data-z="1">1:1</button>
    <button id="bt-kapat">Kapat &times;</button>
  </div>
  <div class="bt-alan" id="bt-alan"><img id="bt-img" alt=""></div>
  <div class="bt-ipucu">tekerlek: yakinlastir · surukle: kaydir · cift tikla: 1:1 &harr; sigdir · ESC: kapat</div>
</div>

<script>
const b1=document.getElementById('btn-belge'),b2=document.getElementById('btn-ham');
function mod(h){{document.body.classList.toggle('ham-mod',h);
b1.classList.toggle('aktif',!h);b2.classList.toggle('aktif',h);}}
b1.onclick=()=>mod(false);b2.onclick=()=>mod(true);

/* ---- sutun goster/gizle ---- */
function sutunGuncelle(){{
  const acik=[...document.querySelectorAll('.sutun-secim input')]
    .filter(c=>c.checked).map(c=>c.dataset.sut);
  document.querySelectorAll('.sut').forEach(s=>{{
    s.style.display = acik.includes(s.dataset.parser) ? '' : 'none';
  }});
  /* Sutun sayisini elle set ETMIYORUZ -- grid-auto-columns minmax() ile
     yer varsa esit boluyor, yoksa asgari genislikte tutup kaydiriyor. */
}}
document.querySelectorAll('.sutun-secim input')
  .forEach(c=>c.addEventListener('change',sutunGuncelle));
sutunGuncelle();

/* ---- surukleyerek yatay kaydirma (basili tut + sag/sol) ---- */
document.querySelectorAll('.izgara').forEach(g=>{{
  let bas=false, x0=0, s0=0;
  g.addEventListener('pointerdown',e=>{{
    if(e.target.closest('.md,a,button,input,img')) return;  /* metin secimini bozma */
    bas=true; x0=e.clientX; s0=g.scrollLeft; g.classList.add('suruk');
  }});
  g.addEventListener('pointermove',e=>{{
    if(!bas) return; g.scrollLeft = s0 - (e.clientX - x0);
  }});
  ['pointerup','pointerleave','pointercancel'].forEach(t=>
    g.addEventListener(t,()=>{{bas=false; g.classList.remove('suruk');}}));
}});

/* ---- sutun genisligi kaydiricisi ---- */
const genis=document.getElementById('sut-genislik'), genisEt=document.getElementById('sut-genislik-d');
if(genis){{
  const uygula=()=>{{
    document.documentElement.style.setProperty('--sut-min', genis.value+'px');
    genisEt.textContent = genis.value+'px';
  }};
  genis.addEventListener('input',uygula); uygula();
}}

/* ---- buyutec: yakinlastir / kaydir ---- */
const kutu=document.getElementById('buyutec'), alan=document.getElementById('bt-alan'),
      bimg=document.getElementById('bt-img'), oranEt=document.getElementById('bt-oran'),
      baslik=document.getElementById('bt-baslik');
let z=1, tx=0, ty=0, suruk=false, sx=0, sy=0, sigdirZ=1;

function uygula(){{
  bimg.style.transform=`translate(${{tx}}px,${{ty}}px) scale(${{z}})`;
  oranEt.textContent=Math.round(z*100)+'%';
}}
function sigdir(){{
  const a=alan.clientWidth/bimg.naturalWidth, b=alan.clientHeight/bimg.naturalHeight;
  sigdirZ=Math.min(a,b)*0.97; z=sigdirZ; tx=0; ty=0; uygula();
}}
function ac(src,ad){{
  bimg.src=src; baslik.textContent=ad;
  kutu.classList.add('acik'); document.body.style.overflow='hidden';
  if(bimg.complete) sigdir(); else bimg.onload=sigdir;
}}
function kapat(){{kutu.classList.remove('acik'); document.body.style.overflow='';}}

document.querySelectorAll('img.buyutulebilir').forEach(im=>{{
  im.addEventListener('click',()=>ac(im.src, im.alt));
}});
document.getElementById('bt-kapat').onclick=kapat;
kutu.addEventListener('click',e=>{{if(e.target===kutu||e.target===alan) kapat();}});
document.addEventListener('keydown',e=>{{
  if(!kutu.classList.contains('acik')) return;
  if(e.key==='Escape') kapat();
  if(e.key==='+'||e.key==='=') {{z=Math.min(z*1.25,8); uygula();}}
  if(e.key==='-') {{z=Math.max(z/1.25,0.05); uygula();}}
}});
document.querySelectorAll('.bt-cubuk button[data-z]').forEach(b=>{{
  b.onclick=e=>{{e.stopPropagation();
    const v=b.dataset.z;
    if(v==='+') z=Math.min(z*1.25,8);
    else if(v==='-') z=Math.max(z/1.25,0.05);
    else if(v==='sigdir') return sigdir();
    else {{z=1; tx=0; ty=0;}}
    uygula();}};
}});
alan.addEventListener('wheel',e=>{{
  e.preventDefault();
  const onceki=z;
  z=Math.min(Math.max(z*(e.deltaY<0?1.15:1/1.15),0.05),8);
  /* imlecin oldugu noktayi sabit tut */
  const r=alan.getBoundingClientRect();
  const mx=e.clientX-r.left-r.width/2-tx, my=e.clientY-r.top-r.height/2-ty;
  tx-=mx*(z/onceki-1); ty-=my*(z/onceki-1);
  uygula();
}},{{passive:false}});
alan.addEventListener('mousedown',e=>{{suruk=true;sx=e.clientX-tx;sy=e.clientY-ty;
  alan.classList.add('suruklinuyor');e.preventDefault();}});
window.addEventListener('mousemove',e=>{{if(!suruk)return;tx=e.clientX-sx;ty=e.clientY-sy;uygula();}});
window.addEventListener('mouseup',()=>{{suruk=false;alan.classList.remove('suruklinuyor');}});
alan.addEventListener('dblclick',()=>{{if(Math.abs(z-1)<0.01) sigdir(); else {{z=1;tx=0;ty=0;uygula();}}}});
</script></body></html>"""


CSS = """
:root{--bg:#f6f7f9;--kart:#fff;--metin:#1c1f23;--soluk:#6b7280;--cizgi:#e3e6ea;
--vurgu:#b4451f;--vurgu-bg:#fdf4f0;--uyari:#8a5a00;--uyari-bg:#fff8e6;--kod-bg:#f2f3f5;
--yuksek:#c0392b;--orta:#b8860b;--dusuk:#5f8a5f}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#14171a;--kart:#1c2024;--metin:#e6e8ea;--soluk:#9aa3ad;--cizgi:#2c3238;
--vurgu:#ff9f7a;--vurgu-bg:#2a1d17;--uyari:#e8c37a;--uyari-bg:#2a2312;--kod-bg:#24282d;
--yuksek:#ff8a7a;--orta:#e8c37a;--dusuk:#8fbf8f}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--metin);
font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif}
.ust{position:sticky;top:0;z-index:20;display:flex;justify-content:space-between;
align-items:center;gap:16px;padding:10px 18px;background:var(--kart);
border-bottom:1px solid var(--cizgi);flex-wrap:wrap}
.ust-sol{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.geri{color:var(--vurgu);text-decoration:none;font-weight:600}
.kucuk{color:var(--soluk);font-size:13px}
.segment{display:flex;border:1px solid var(--cizgi);border-radius:8px;overflow:hidden}
.segment button{border:0;background:transparent;color:var(--metin);padding:7px 16px;
cursor:pointer;font-size:14px}
.segment button.aktif{background:var(--vurgu);color:#fff}
.sayfa-nav{padding:8px 18px;color:var(--soluk);font-size:13px;line-height:2}
.sayfa-nav a{display:inline-block;margin-right:5px;padding:2px 8px;
border:1px solid var(--cizgi);border-radius:6px;color:var(--metin);text-decoration:none}
.sayfa-nav a.yuksek{border-color:var(--yuksek);color:var(--yuksek);font-weight:600}
.sayfa-nav a:hover{border-color:var(--vurgu);color:var(--vurgu)}
.uyari-kutu{margin:10px 18px;padding:12px 16px;background:var(--uyari-bg);
border:1px solid var(--uyari);border-radius:10px;font-size:13.5px}
.uyari-kutu ul{margin:6px 0 0;padding-left:20px}.uyari-kutu li{margin:3px 0}
.uyari-kutu p{margin:8px 0 0}
.sayfa{margin:18px}
.sayfa-baslik{display:flex;align-items:center;gap:12px;font-weight:700;font-size:17px;
margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid var(--vurgu)}
.puan{font-size:12px;font-weight:600;padding:2px 9px;border-radius:20px;
border:1px solid currentColor}
.puan.yuksek{color:var(--yuksek)}.puan.orta{color:var(--orta)}.puan.dusuk{color:var(--dusuk)}
/* Yatay kaydirma: 6 parser yan yana sigmadigi icin sutunlar sabit asgari
   genislikte tutulur, tasan kisim kaydirilir. Boylece hicbir sutun okunamayacak
   kadar daralmiyor. Sutun genisligi --sut-min ile ayarlanabilir (kaydirici). */
.izgara{display:grid;grid-auto-flow:column;
  grid-auto-columns:minmax(var(--sut-min,360px),1fr);
  gap:12px;align-items:start;overflow-x:auto;overscroll-behavior-x:contain;
  padding-bottom:14px;scrollbar-color:var(--soluk) var(--kod-bg)}
.izgara.suruk{cursor:grabbing;user-select:none}
.izgara::-webkit-scrollbar{height:14px}
.izgara::-webkit-scrollbar-track{background:var(--kod-bg);border-radius:7px}
.izgara::-webkit-scrollbar-thumb{background:var(--soluk);border-radius:7px;
  border:3px solid var(--kart)}
.izgara::-webkit-scrollbar-thumb:hover{background:var(--vurgu)}
.genislik-ayar{display:inline-flex;align-items:center;gap:7px;font-size:13px}
.genislik-ayar input[type=range]{width:130px;accent-color:var(--vurgu)}
.sekmeler{display:flex;gap:4px;margin-right:6px}
.sekmeler a{padding:5px 14px;border-radius:8px;text-decoration:none;
color:var(--metin);border:1px solid var(--cizgi);font-size:14px}
.sekmeler a:hover{border-color:var(--vurgu);color:var(--vurgu)}
.sutun-secim{display:flex;flex-wrap:wrap;gap:14px;align-items:center;
padding:8px 18px;color:var(--soluk);font-size:13px;
border-bottom:1px solid var(--cizgi)}
.sutun-secim label{display:inline-flex;align-items:center;gap:5px;
color:var(--metin);cursor:pointer}
.sut{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;
overflow:hidden;display:flex;flex-direction:column}
.sut header{padding:9px 12px;border-bottom:1px solid var(--cizgi);background:var(--kod-bg)}
.sut h3{margin:0;font-size:13px;letter-spacing:.04em;text-transform:uppercase}
.sut .alt{display:block;color:var(--soluk);font-size:11.5px;margin-top:2px}
.sut-pdf header{background:var(--vurgu-bg)}
.icerik{padding:12px;max-height:80vh;overflow:auto}
.icerik img{max-width:100%;height:auto;border:1px solid var(--cizgi);border-radius:6px}
.sut-pdf .icerik img{width:100%}
.icerik p{margin:0 0 9px}
.icerik h1,.icerik h2,.icerik h3,.icerik h4,.icerik h5,.icerik h6{
margin:12px 0 6px;line-height:1.3;padding-left:8px;border-left:3px solid var(--vurgu)}
.icerik h1{font-size:20px}.icerik h2{font-size:18px}.icerik h3{font-size:16px}
.icerik h4,.icerik h5,.icerik h6{font-size:14.5px}
.icerik table{border-collapse:collapse;width:100%;font-size:12px;margin:8px 0}
.icerik th,.icerik td{border:1px solid var(--cizgi);padding:3px 6px;
text-align:left;vertical-align:top}
.icerik th{background:var(--kod-bg);font-weight:600}
.tbl-uyari{font-size:11.5px;color:var(--uyari);background:var(--uyari-bg);
border:1px solid var(--uyari);border-radius:6px;padding:3px 8px;margin:6px 0 2px}
code{background:var(--kod-bg);padding:1px 4px;border-radius:4px;font-size:12.5px}
.bos{color:var(--soluk);font-style:italic}
pre.v-ham{display:none;margin:0;white-space:pre-wrap;word-break:break-word;
font:12px/1.5 ui-monospace,Consolas,monospace;background:var(--kod-bg);
padding:10px;border-radius:6px}
body.ham-mod .v-belge{display:none}
body.ham-mod pre.v-ham{display:block}

/* ---- buyutec ---- */
img.buyutulebilir{cursor:zoom-in;transition:border-color .15s}
img.buyutulebilir:hover{border-color:var(--vurgu)}
.buyutec{display:none;position:fixed;inset:0;z-index:100;background:rgba(8,10,12,.93);
flex-direction:column}
.buyutec.acik{display:flex}
.bt-cubuk{display:flex;align-items:center;gap:10px;padding:10px 16px;
background:var(--kart);border-bottom:1px solid var(--cizgi);flex-wrap:wrap}
.bt-cubuk span{color:var(--metin);font-size:14px}
#bt-baslik{font-weight:600;margin-right:auto}
#bt-oran{min-width:56px;text-align:center;font-variant-numeric:tabular-nums;
color:var(--soluk)}
.bt-cubuk button{border:1px solid var(--cizgi);background:transparent;color:var(--metin);
padding:5px 13px;border-radius:7px;cursor:pointer;font-size:14px}
.bt-cubuk button:hover{border-color:var(--vurgu);color:var(--vurgu)}
#bt-kapat{border-color:var(--vurgu);color:var(--vurgu)}
.bt-alan{flex:1;overflow:hidden;display:flex;align-items:center;justify-content:center;
cursor:grab}
.bt-alan.suruklinuyor{cursor:grabbing}
#bt-img{transform-origin:center center;image-rendering:auto;
box-shadow:0 6px 40px rgba(0,0,0,.6);background:#fff;user-select:none;
max-width:none;max-height:none}
.bt-ipucu{padding:8px 16px;text-align:center;color:#9aa3ad;font-size:12.5px;
background:var(--kart);border-top:1px solid var(--cizgi)}
"""


def index_html(kayitlar) -> str:
    kartlar = "".join(
        f'<div class="kart"><a href="{stem}.html"><strong>{stem}</strong></a>'
        f'<span>{gost} / {top} sayfa · ort. anlasmazlik {ort:.2f}</span>'
        f'<a class="alt-bag" href="annot_{stem}.html">etiketli gorunum →</a></div>'
        for stem, gost, top, ort in kayitlar
    )
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PDF parser karsilastirmasi</title><style>{CSS}
.kartlar{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
gap:12px;margin:18px}}
.kart{{display:flex;flex-direction:column;gap:4px;padding:16px;background:var(--kart);
border:1px solid var(--cizgi);border-radius:10px;color:var(--metin)}}
.kart > a{{text-decoration:none;color:var(--metin)}}
.kart:hover{{border-color:var(--vurgu)}}.kart span{{color:var(--soluk);font-size:13px}}
.kart .alt-bag{{margin-top:6px;font-size:12.5px;color:var(--vurgu);text-decoration:none}}
.kart .alt-bag:hover{{text-decoration:underline}}
.giris{{margin:18px;max-width:880px}}
</style></head><body>
<div class="ust"><div class="ust-sol">
<nav class="sekmeler"><a href="index.html" class="aktif-sekme">Belgeler</a><a href="annot_index.html">Etiketli gorunum</a><a href="olcumler.html">Olcumler</a><a href="mineru.html">MinerU</a></nav>
<strong>PDF parser karsilastirmasi</strong>
<span class="kucuk">pypdf · pdf-inspector · opendataloader · pymupdf4llm</span></div></div>
<div class="giris">
<p>Her sayfa dort sutunda: solda <b>gercek PDF sayfasi</b> (hakem), sagda uc
parser'in ayni sayfa icin urettigi cikti.</p>
<p><b>Belge / Ham metin</b> dugmesiyle gorunum degisir. Tablo hizasi gibi kusurlari
degerlendirirken <b>Ham metin</b>'i kullan — Belge gorunumu bozuk tabloyu duzeltip
gosterir ve kusuru gizler.</p>
<p><b>Adalet:</b> uc cikti da ayni Markdown donusturucusunden, ayni ayarlarla gecer.
opendataloader'in kendi (daha guzel) HTML ciktisi karsilastirmada kullanilmaz;
her belgenin sayfasinda "kiyas disi" etiketiyle ayri baglanti olarak durur.</p>
<p><b>Sayfa secimi:</b> kisa belgelerin tamami basilir. Uzun belgelerde sayfalar
<b>anlasmazlik puani</b> ile siralanir — puan hicbir parser'i dogru varsaymaz,
sadece uc ciktinin birbirinden ne kadar ayristigini olcer. Boylece "sorunlu sayfa"
elle secilmemis olur.</p>
</div><div class="kartlar">{kartlar}</div></body></html>"""


# ======================================================================
#  ANA AKIS
# ======================================================================

def main() -> None:
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].lower()
    hepsi = "--hepsi" in sys.argv

    os.makedirs(ASSETS_DIR, exist_ok=True)
    os.makedirs(ODL_ASSETS, exist_ok=True)
    kayitlar = []

    for stem in BELGELER:
        if only and only not in stem.lower():
            continue
        pdf_path = os.path.join(CORPUS_DIR, stem + ".pdf")
        if not os.path.exists(pdf_path):
            print(f"  ATLANDI (PDF yok): {stem}")
            continue

        print(f"\n=== {stem} ===")
        doc = pymupdf.open(pdf_path)
        toplam = doc.page_count
        doc.close()

        print("  parserlar calisiyor...", end=" ", flush=True)
        odl_sayfalar, odl_html, odl_gorsel = odl_pages(pdf_path, stem)
        ciktilar = {
            "pypdf": pypdf_pages(pdf_path),
            "insp": inspector_pages(pdf_path),
            "odl": odl_sayfalar,
            "p4llm": p4llm_pages(pdf_path),   # yavas (ONNX duzen modeli)
            "mineru": mineru_pages(stem),     # hazir ciktidan okunur
        }
        print("bitti  " + "  ".join(f"{k}={len(v)}s" for k, v in ciktilar.items())
              + f"  odl_gorsel={odl_gorsel}")

        sayfalar, puanlar, aciklama = sayfa_sec(ciktilar, toplam, hepsi)
        ort = sum(puanlar.values()) / max(1, len(puanlar))
        yuksek = [n for n in sayfalar if puanlar.get(n, 0) > 0.45]
        print(f"  secim: {aciklama}  (ort. anlasmazlik {ort:.2f}, "
              f"yuksek sayfa: {yuksek if yuksek else 'yok'})")

        print("  sayfa goruntuleri...", end=" ", flush=True)
        goruntuler = render_sayfalar(pdf_path, stem, sayfalar)
        print(f"{len(goruntuler)} PNG")

        with open(os.path.join(HTML_DIR, f"{stem}.html"), "w", encoding="utf-8") as f:
            f.write(belge_html(stem, sayfalar, goruntuler, ciktilar, toplam,
                               puanlar, aciklama, odl_html, odl_gorsel))
        kayitlar.append((stem, len(sayfalar), toplam, ort))

    if kayitlar:
        with open(os.path.join(HTML_DIR, "index.html"), "w", encoding="utf-8") as f:
            f.write(index_html(kayitlar))
        boyut = sum(os.path.getsize(os.path.join(r, fn))
                    for r, _d, fs in os.walk(HTML_DIR) for fn in fs)
        print(f"\nHazir: html/index.html   (toplam {boyut / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
