"""Olcum sonuclarini gorsellestirir -> html/olcumler.html

Girdi:
    sonuclar.csv            compare.py'in urettigi ham olcumler
    referans_skorlar.csv    referans_skor.py'in urettigi arXiv-referansli skorlar
                            (yoksa o bolum atlanir)

Tasarim notlari
---------------
* Renkler dogrulanmis referans paletinden, BELGELENMIS SIRASIYLA alindi
  (mavi, turuncu, aqua, sari). Palet degistirilmedigi icin palette.md'deki
  dogrulama sonucu gecerlidir: bitisik cift listesinde her iki modda da
  gecer. Dogrulayici scripti bu makinede calistirilamadi (node kurulu degil).
* Acik modda aqua ve sari 3:1 kontrastin altinda kaliyor -> "relief" kurali:
  HER cubuga gorunur deger etiketi konuyor, renk tek basina bilgi tasimiyor.
* Kaynakca kapisi bir CHART degil MATRIS olarak gosteriliyor: veri ikili
  (tetikleniyor / tetiklenmiyor) ve asil soru "hangi belgede hangisi" --
  cubuk grafik bunu gizlerdi.
* Durum renkleri (yesil/kirmizi) ikon+etiketle birlikte kullaniliyor,
  renk tek basina anlam tasimiyor.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\grafik_uret.py
"""
from __future__ import annotations

import csv
import html
import os

# Calisma klasoru: korpus/, out/ ve html/ burada bulunur. Boyutu nedeniyle
# depoya alinmadi -- baska makinede PDF_PARSER_BASE ortam degiskeniyle gosterin:
#     set PDF_PARSER_BASE=C:\yol\sude-staj
BASE = os.environ.get("PDF_PARSER_BASE", r"c:\Users\PC_7820\Desktop\sude-staj")
HTML_DIR = os.path.join(BASE, "html")
CSV_PATH = os.path.join(BASE, "sonuclar.csv")
REF_CSV = os.path.join(BASE, "referans_skorlar.csv")

# Gosterilecek parserlar ve palet slotlari (belgelenmis sira)
PARSERS = [
    ("pypdf_plain", "pypdf", "s1"),
    ("inspector", "pdf-inspector", "s2"),
    ("opendataloader", "opendataloader", "s3"),
    ("pymupdf4llm", "pymupdf4llm", "s4"),
    # MinerU AYRI ortamda (.venv-mineru) ve AYRI donanim sinifinda kosuyor:
    # backend=pipeline, CPU. Bu MinerU'nun TAVANI DEGIL, GPU'suz TABANI
    # (OmniDocBench v1.6: pipeline 86.47 vs vlm/hybrid 95.26-95.69).
    # Hiz karsilastirmasi adil (ayni makine, ayni belgeler); dogruluk
    # karsilastirmasinda bu etiket dusurulmemeli.
    ("mineru", "MinerU (pipeline·CPU)", "s5"),
]
KISA = {k: ad for k, ad, _ in PARSERS}


def oku(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sayi(v, vars=0.0):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return vars


# ======================================================================
#  BILESENLER
# ======================================================================

def cubuk_grubu(baslik, aciklama, veriler, birim="", tersine_iyi=True,
                bicim="{:,.0f}"):
    """veriler: [(etiket, [(parser_key, deger), ...]), ...]

    tersine_iyi=True  -> dusuk deger iyi (kusur sayaci)
    """
    enb = max((d for _, ps in veriler for _, d in ps), default=0) or 1
    satirlar = []
    for etiket, ps in veriler:
        cubuklar = []
        for pk, deger in ps:
            slot = dict((k, s) for k, _, s in PARSERS)[pk]
            gen = max(deger / enb * 100, 0.6) if deger else 0
            cubuklar.append(
                f'<div class="cb" title="{html.escape(KISA[pk])}: '
                f'{bicim.format(deger)}{birim}">'
                f'<div class="cb-dolgu {slot}" style="width:{gen:.2f}%"></div>'
                f'<span class="cb-deger">{bicim.format(deger)}{birim}</span>'
                f'</div>'
            )
        satirlar.append(
            f'<div class="satir"><div class="satir-ad">{html.escape(etiket)}</div>'
            f'<div class="satir-cb">{"".join(cubuklar)}</div></div>'
        )

    yon = "dusuk olan iyi" if tersine_iyi else "yuksek olan iyi"
    return f"""<section class="kart">
<h3>{html.escape(baslik)}</h3>
<p class="alt">{aciklama} <span class="yon">{yon}</span></p>
{efsane()}
<div class="izgara-cubuk">{"".join(satirlar)}</div>
</section>"""


def efsane():
    ogeler = "".join(
        f'<span class="ef"><i class="nokta {s}"></i>{html.escape(ad)}</span>'
        for _, ad, s in PARSERS
    )
    return f'<div class="efsane">{ogeler}</div>'


def kapi_matrisi(rows):
    """Kaynakca kapisi: hangi belgede hangi parser tetikliyor."""
    bas = "".join(f"<th>{html.escape(ad)}</th>" for _, ad, _ in PARSERS)
    govde = []
    for r in rows:
        hucreler = []
        for pk, _, _ in PARSERS:
            var = str(r.get(f"{pk}_kapi_var", "")).strip().lower() == "true"
            bul = r.get(f"{pk}_kapi_basliklar", "") or ""
            if var:
                hucreler.append(
                    f'<td class="d-iyi" title="{html.escape(bul[:120])}">'
                    f'<span class="ikon">&check;</span> var</td>')
            else:
                hucreler.append(
                    '<td class="d-kotu"><span class="ikon">&times;</span> yok</td>')
        govde.append(f'<tr><th class="sol">{html.escape(r["dosya"])}</th>'
                     f'{"".join(hucreler)}</tr>')

    return f"""<section class="kart">
<h3>Kaynakça filtresi tetikleniyor mu?</h3>
<p class="alt">Sistemdeki <code>evidence_quality.is_non_evidence_section()</code>
kapısı yalnızca Markdown başlıklarına bakar. Bir parser <code>References</code> /
<code>Kaynakça</code> başlığını üretemezse kaynakça girdileri kanıt sayılabilir.
Hücrenin üzerine gelince yakalanan başlık görünür.</p>
<div class="tablo-sar"><table class="matris">
<thead><tr><th class="sol">belge</th>{bas}</tr></thead>
<tbody>{"".join(govde)}</tbody></table></div>
<p class="not"><b>Dikkat:</b> "var" her zaman <i>kaynakça</i> başlığı demek değil.
sybil'de opendataloader kapıyı <code>APPENDIX</code> ile tetikliyor ve o başlık
kaynakça listesinden <i>sonra</i> geldiği için listeyi korumuyor. Hücreye gelip
yakalanan başlığı kontrol et.</p>
</section>"""


def siralama_tablosu(ref):
    """opendataloader-bench'in siralama tablosuyla AYNI SUTUN DUZENI."""
    ozet = []
    for pk, ad, slot in PARSERS:
        alt = [r for r in ref if r["parser"] == pk]
        if not alt:
            continue

        def ort(k):
            d = [sayi(r[k]) for r in alt if str(r.get(k, "")).strip() != ""]
            return sum(d) / len(d) if d else 0.0

        ozet.append((ad, slot, ort("genel"), ort("nid"), ort("teds"), ort("mhs")))
    ozet.sort(key=lambda x: -x[2])

    satirlar = []
    for i, (ad, slot, g, n, t, m) in enumerate(ozet):
        vurgu = ' class="lider"' if i == 0 else ""
        satirlar.append(
            f'<tr{vurgu}><th class="sol"><i class="nokta {slot}"></i>'
            f'{html.escape(ad)}</th>'
            f'<td class="ana">{g:.3f}</td><td>{n:.3f}</td>'
            f'<td>{t:.3f}</td><td>{m:.3f}</td></tr>')

    return f"""<section class="kart">
<h3>Sıralama — kendi korpusumuzda</h3>
<p class="alt">opendataloader-bench'in sıralama tablosuyla <b>aynı sütun düzeni</b>:
Overall = üç metriğin ortalaması. Referans, makalelerin
<b>arXiv HTML</b>'i (LaTeXML ile LaTeX kaynağından üretilmiş).</p>
<div class="tablo-sar"><table class="siralama">
<thead><tr><th class="sol">ENGINE</th><th class="ana">OVERALL</th>
<th>READING ORDER</th><th>TABLES</th><th>HEADINGS</th></tr></thead>
<tbody>{"".join(satirlar)}</tbody></table></div>
<p class="not"><b>Bu tablo onların yayınladığı sayılarla kıyaslanamaz.</b> Üç sebeple:
(1) metrikler aynı <i>fikrin</i> burada yazılmış karşılığı, aynı kod değil;
(2) korpus farklı — onlarınki 200 belge, bizimki 6;
(3) <b>en zor iki belgemiz (sybil, turkce) arXiv'de olmadığı için burada yok</b> —
skorlar gerçekte olduğundan iyimserdir.</p>
</section>"""


def veri_tablosu(baslik, basliklar, satirlar):
    b = "".join(f"<th>{html.escape(x)}</th>" for x in basliklar)
    g = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in s)
                + "</tr>" for s in satirlar)
    return f"""<details class="veri"><summary>{html.escape(baslik)} — sayı tablosu</summary>
<div class="tablo-sar"><table class="veri-tbl"><thead><tr>{b}</tr></thead>
<tbody>{g}</tbody></table></div></details>"""


# ======================================================================
#  SAYFA
# ======================================================================

def main() -> None:
    rows = oku(CSV_PATH)
    if not rows:
        print("sonuclar.csv yok veya bos.")
        return
    ref = oku(REF_CSV)
    mevcut = [p for p in PARSERS
              if any(r.get(f"{p[0]}_karakter") for r in rows)]
    if len(mevcut) < len(PARSERS):
        eksik = [p[1] for p in PARSERS if p not in mevcut]
        print(f"  UYARI: su parserlarin verisi yok, atlanacak: {eksik}")

    bolumler = []

    # ---- 1. kaynakca kapisi ----
    bolumler.append(kapi_matrisi(rows))

    # ---- 2. ligatur ----
    lig = [(r["dosya"], [(pk, sayi(r.get(f"{pk}_ligatur")))
                         for pk, _, _ in PARSERS]) for r in rows]
    lig = [(a, ps) for a, ps in lig if any(d for _, d in ps)]
    if lig:
        bolumler.append(cubuk_grubu(
            "Ligatür kalıntısı", "Çıktıda <code>ﬁ ﬂ ﬀ</code> tek karakter olarak "
            "kalmış. Kalırsa kelime araması bozulur: <code>different</code> "
            "aranınca <code>di\ufb00erent</code> eşleşmez. <b>Ölçüt 2'yi bozar.</b>", lig))

    # ---- 3. tireleme ----
    tire = [(r["dosya"], [(pk, sayi(r.get(f"{pk}_tireleme")))
                          for pk, _, _ in PARSERS]) for r in rows]
    tire = [(a, ps) for a, ps in tire if any(d for _, d in ps)]
    if tire:
        bolumler.append(cubuk_grubu(
            "Birleşmemiş satır sonu tirelemesi",
            "<code>repre-</code> / <code>sentation</code> birleştirilmemiş. "
            "Ligatür gibi bu da alıntı eşleşmesini bozar. <b>Ölçüt 2'yi bozar.</b>", tire))

    # ---- 4. hiz ----
    hiz = [(r["dosya"], [(pk, sayi(r.get(f"{pk}_sure_sn")))
                         for pk, _, _ in PARSERS]) for r in rows]
    hiz = [(a, ps) for a, ps in hiz if any(d for _, d in ps)]
    if hiz:
        bolumler.append(cubuk_grubu(
            "Süre (medyan, saniye)",
            "opendataloader JVM açılışını içerir (~0,5–0,8 sn sabit); "
            "pymupdf4llm ONNX düzen modeli çalıştırır. Diğer ikisi aynı Python "
            "sürecinde koşar — <b>hız kıyası bu yönüyle eşit değildir.</b>",
            hiz, birim=" sn", bicim="{:,.2f}"))

    # ---- 5. arXiv referansli skorlar ----
    if ref:
        bolumler.insert(0, siralama_tablosu(ref))
        for metrik, ad, acik in (
            ("teds", "Tablo yapısı (TEDS-benzeri)",
             "Tabloyu ağaca çevirip (table &gt; tr &gt; td) referanstaki tabloyla "
             "arasındaki düzenleme mesafesini ölçer. <b>Ölçüt 4'ü</b> doğrudan "
             "sorar: bir sayı doğru hücrede mi."),
            ("f1", "Başlık F1 (arXiv referansına göre)",
             "Kesinlik = ürettiği başlıkların kaçı gerçek. Duyarlılık = gerçek "
             "başlıkların kaçını buldu. F1 ikisinin dengesi. <b>Ölçüt 3.</b>"),
            ("nid", "Metin benzerliği (NID-benzeri)",
             "Çıkarılan metnin arXiv HTML referansına yakınlığı. "
             "<b>Dört parser da 0,83–0,86 arasında — bu metrik ayırt etmiyor.</b>"),
        ):
            veri = {}
            for r in ref:
                veri.setdefault(r["dosya"], []).append(
                    (r["parser"], sayi(r.get(metrik))))
            liste = [(d, [(pk, dict(v).get(pk, 0.0)) for pk, _, _ in PARSERS])
                     for d, v in veri.items()]
            bolumler.append(cubuk_grubu(
                ad, acik + " <b>Bu bölüm yalnızca 6 arXiv belgesini kapsar; "
                "korpusun en zor ikisi (sybil, turkce) arXiv'de olmadığı için "
                "burada yok — skorlar gerçekte olduğundan iyimserdir.</b>",
                liste, tersine_iyi=False, bicim="{:.3f}"))

        bolumler.append(veri_tablosu(
            "arXiv referanslı skorlar",
            ["belge", "parser", "genel", "NID", "TEDS", "MHS", "F1", "kesinlik",
             "duyarlılık", "aday başlık", "ref başlık", "aday tablo", "ref tablo"],
            [[r["dosya"], KISA.get(r["parser"], r["parser"]), r.get("genel", ""),
              r["nid"], r.get("teds", ""), r["mhs"], r["f1"], r["kesinlik"],
              r["duyarlilik"], r["aday_baslik"], r["ref_baslik"],
              r.get("aday_tablo", ""), r.get("ref_tablo", "")] for r in ref]))

    # ---- ham veri tablosu ----
    bolumler.append(veri_tablosu(
        "Ham ölçümler",
        ["belge", "parser", "süre (sn)", "karakter", "başlık", "ligatür",
         "tireleme", "sayfa mobilyası"],
        [[r["dosya"], ad, r.get(f"{pk}_sure_sn", "-"),
          r.get(f"{pk}_karakter", "-"), r.get(f"{pk}_baslik", "-"),
          r.get(f"{pk}_ligatur", "-"), r.get(f"{pk}_tireleme", "-"),
          r.get(f"{pk}_sayfa_mobilyasi", "-")]
         for r in rows for pk, ad, _ in PARSERS
         if r.get(f"{pk}_karakter")]))

    sayfa = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ölçümler — parser karşılaştırması</title><style>{CSS}</style></head>
<body class="viz-root">
<div class="ust"><div class="ust-sol">
  <nav class="sekmeler"><a href="index.html">Belgeler</a><a href="annot_index.html">Etiketli görünüm</a><a href="olcumler.html" class="aktif-sekme">Ölçümler</a><a href="mineru.html">MinerU</a></nav>
  <strong>Ölçümler</strong>
  <span class="kucuk">{len(rows)} belge · {len(mevcut)} parser</span>
</div></div>
<div class="giris">
<p>Bu sayfa <code>compare.py</code> ve <code>referans_skor.py</code> çıktılarından
otomatik üretilir. Sayfa görüntüsü karşılaştırması için
<a href="index.html">belgeler</a> sayfasına git.</p>
<p><b>Doğruluk ölçütü:</b> bir çıktı şu dördünden birini bozuyorsa hata sayılır —
(1) cümleler bütün olmalı, (2) alıntılar birebir bulunabilmeli, (3) pasajın hangi
bölümden geldiği bilinmeli, (4) bir sayının hangi satır/sütuna ait olduğu belli
olmalı. Sadece daha çirkin görünmek hata değildir.</p>
</div>
{"".join(bolumler)}
<div class="giris"><p class="not">Renkler doğrulanmış referans paletinden,
belgelenmiş sırasıyla alınmıştır. Açık modda düşük kontrastlı slotlar için her
çubukta görünür değer etiketi vardır — renk tek başına bilgi taşımaz.</p></div>
</body></html>"""

    os.makedirs(HTML_DIR, exist_ok=True)
    hedef = os.path.join(HTML_DIR, "olcumler.html")
    with open(hedef, "w", encoding="utf-8") as f:
        f.write(sayfa)
    print(f"Hazir: {os.path.relpath(hedef, BASE)}")
    print(f"  bolum: {len(bolumler)}   parser: {[p[1] for p in mevcut]}")
    if not ref:
        print("  NOT: referans_skorlar.csv yok -> arXiv skor bolumleri atlandi")


CSS = """
.viz-root{
  --yuzey:#fcfcfb; --duzlem:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e;
  --soluk:#898781; --izgara:#e1e0d9; --eksen:#c3c2b7;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s5:#7a5ad9;
  --iyi:#0ca30c; --kotu:#d03b3b; --cerceve:rgba(11,11,11,.10);
}
@media (prefers-color-scheme: dark){:root:where(:not([data-theme="light"])) .viz-root{
  --yuzey:#1a1a19; --duzlem:#0d0d0d; --ink:#fff; --ink2:#c3c2b7;
  --soluk:#898781; --izgara:#2c2c2a; --eksen:#383835;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#9b7de8;
  --iyi:#0ca30c; --kotu:#d03b3b; --cerceve:rgba(255,255,255,.10);
}}
:root[data-theme="dark"] .viz-root{
  --yuzey:#1a1a19; --duzlem:#0d0d0d; --ink:#fff; --ink2:#c3c2b7;
  --soluk:#898781; --izgara:#2c2c2a; --eksen:#383835;
  --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s5:#9b7de8;
  --iyi:#0ca30c; --kotu:#d03b3b; --cerceve:rgba(255,255,255,.10);
}
*{box-sizing:border-box}
body{margin:0;background:var(--duzlem);color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
.ust{position:sticky;top:0;z-index:10;display:flex;gap:16px;align-items:center;
  padding:10px 18px;background:var(--yuzey);border-bottom:1px solid var(--cerceve)}
.ust-sol{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.geri{color:var(--s2);text-decoration:none;font-weight:600}
.sekmeler{display:flex;gap:4px;margin-right:6px}
.sekmeler a{padding:5px 14px;border-radius:8px;text-decoration:none;
  color:var(--ink);border:1px solid var(--cerceve);font-size:14px}
.sekmeler a:hover{border-color:var(--s2);color:var(--s2)}
.sekmeler a.aktif-sekme{background:var(--s1);color:#fff;border-color:var(--s1)}
.kucuk{color:var(--soluk);font-size:13px}
.giris{margin:18px;max-width:900px;color:var(--ink2)}
.giris p{margin:0 0 10px}
.kart{margin:18px;padding:18px;background:var(--yuzey);
  border:1px solid var(--cerceve);border-radius:12px}
.kart h3{margin:0 0 4px;font-size:17px}
.kart .alt{margin:0 0 14px;color:var(--ink2);font-size:13.5px;max-width:900px}
.yon{display:inline-block;margin-left:6px;padding:1px 8px;border-radius:20px;
  border:1px solid var(--eksen);color:var(--soluk);font-size:11.5px}
.efsane{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:12px;
  padding-bottom:10px;border-bottom:1px solid var(--izgara)}
.ef{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--ink2)}
.nokta{width:11px;height:11px;border-radius:3px;display:inline-block}
.s1{background:var(--s1)} .s2{background:var(--s2)}
.s3{background:var(--s3)} .s4{background:var(--s4)}
.s5{background:var(--s5)}
.izgara-cubuk{display:flex;flex-direction:column;gap:14px}
.satir{display:grid;grid-template-columns:190px 1fr;gap:14px;align-items:center}
@media(max-width:760px){.satir{grid-template-columns:1fr}}
.satir-ad{font-size:13px;color:var(--ink2);word-break:break-word}
.satir-cb{display:flex;flex-direction:column;gap:2px}
.cb{display:flex;align-items:center;gap:8px;height:16px}
.cb-dolgu{height:11px;border-radius:0 4px 4px 0;min-width:2px;
  transition:filter .12s}
.cb:hover .cb-dolgu{filter:brightness(1.12)}
.cb-deger{font-size:11.5px;color:var(--ink2);font-variant-numeric:tabular-nums;
  white-space:nowrap}
.tablo-sar{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid var(--izgara);padding:6px 9px;text-align:left}
thead th{background:var(--duzlem);color:var(--ink2);font-weight:600;
  position:sticky;top:0}
th.sol{background:var(--duzlem);font-weight:600}
.matris td{text-align:center;font-size:12.5px;white-space:nowrap}
.siralama td{text-align:right;font-variant-numeric:tabular-nums;font-size:13.5px}
.siralama th.ana,.siralama td.ana{font-weight:700}
.siralama tr.lider{background:color-mix(in srgb,var(--s2) 10%,transparent)}
.siralama tr.lider th.sol,.siralama tr.lider td{color:var(--s2)}
.siralama th.sol{display:flex;align-items:center;gap:8px;border:0}
.siralama thead th{text-align:right;font-size:11.5px;letter-spacing:.04em}
.siralama thead th.sol{text-align:left}
.ikon{font-weight:700;margin-right:3px}
.d-iyi{color:var(--iyi)} .d-kotu{color:var(--kotu)}
.not{margin:12px 0 0;padding:10px 12px;background:var(--duzlem);
  border-left:3px solid var(--s2);border-radius:0 8px 8px 0;
  font-size:13px;color:var(--ink2)}
.veri{margin:18px;background:var(--yuzey);border:1px solid var(--cerceve);
  border-radius:12px;padding:12px 18px}
.veri summary{cursor:pointer;font-weight:600}
.veri .tablo-sar{margin-top:12px;max-height:60vh;overflow:auto}
.veri-tbl td{font-variant-numeric:tabular-nums}
code{background:var(--duzlem);padding:1px 5px;border-radius:4px;font-size:12.5px}
"""


if __name__ == "__main__":
    main()
