"""Kendi korpusumuzun 261 sayfasini sayfa sayfa gozle inceleme arayuzu (v1).

Sorun: yonlendirme kararlarinin dogrulugu bugune kadar yalniz CSV/JSON'dan
okunabiliyordu. "Bu sayfada gercekten tablo var miydi", "Docling gercekten daha
mi iyi cikardi" sorulari sayfaya bakmadan cevaplanamaz.

Her sayfa icin uretilenler:

  * Sayfanin goruntusu, uzerinde REFERANS kutulari (yesil tablo / mavi sekil).
  * Yol karari (HIZLI / AGIR / OCR), gerekcesi, kalite skoru.
  * Tespit hukmu: tablo ve sekil icin TP / FP / FN.
  * Yonlendirme hukmu: BOSA gonderildi mi, KACIRILDI mi.
  * UC METIN yan yana: fast (pdf-inspector), heavy (Docling), secilen (merge).
  * Critic sayfa skoru fast vs heavy ve farki.
  * Sureler: inspector, kapi, critic, merge (olculdu) + heavy (amortize).
  * Fallback / karantina durumu -- uretimdeki `birlestir()` fonksiyonundan.

REFERANS: tabloda MinerU ile Docling'in ANLASTIGI sayfalar, sekilde Docling'in
picture ogeleri. Gumus referans -- elle dogrulanmadi. kapi_dogrula.py ile AYNI
kural, boylece sayilar oradaki TP/FP/FN ile karsilastirilabilir.

NE OLCMEZ: bu korpusun metin referansi yok. "Kalite farki" sutunu critic'in
BOZULMA skorudur (0-100), referansa gore dogruluk DEGILDIR. C1'deki utility
metrigi burada uygulanamaz.

Kullanim
--------
    .\\.venv\\Scripts\\python.exe src\\hata_arayuzu.py
    -> html/hata_arayuzu.html
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))
from uretim_yolu import ekle  # noqa: E402

ekle()
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pymupdf  # noqa: E402

from research_platform.parsers.smart_pdf import SmartPdfParser  # noqa: E402
from research_platform.parsers.smart_router import SmartRouterHatti  # noqa: E402
from research_platform.parsers.smart_router.engines import EngineResult  # noqa: E402
from research_platform.parsers.smart_router.merge import birlestir  # noqa: E402

CORPUS = os.path.join(BASE, "corpus")
OUT = os.path.join(BASE, "out")
HTML = os.path.join(BASE, "html")
GORSEL = os.path.join(HTML, "hata_gorsel")

BELGELER = ["turkce_makale", "resnet_2sutun_gorsel", "vgg_tablo_agirlikli",
            "attention_tablo", "bert_2sutun_dipnot", "sybil_tip_2sutun",
            "gpt3_uzun_75sayfa", "gpt4_uzun_gorsel",
            "taranmis_bert_2sutun_dipnot"]

#: Sayfa goruntusu buyutme carpani. 1.5 ~ 108 dpi; okunur ve dosya kucuk kalir.
ZOOM = 1.5

#: Router hattinin suresi kac kez olculup medyani alinacak.
KOSU = 3

#: Arayuze gomulen metin sinirı. Uzun sayfalarda dosya sismesin diye kirpilir;
#: kirpilan yer metnin sonunda acikca yazilir.
METIN_SINIR = 6000


# --------------------------------------------------------------- referans
def referans(stem: str) -> tuple[set, set, list, list]:
    """Tablo sayfalari, sekil sayfalari ve cizilecek kutular.

    Tablo referansi = MinerU ile Docling'in ANLASTIGI sayfalar (kapi_dogrula.py
    ile ayni gumus referans). Sekil referansi = Docling'in picture ogeleri.
    """
    with open(os.path.join(OUT, "docling_annot", stem + ".json"), encoding="utf-8") as f:
        annot = json.load(f)

    mineru = set()
    yol = os.path.join(OUT, "mineru", stem, "auto", stem + "_middle.json")
    if os.path.exists(yol):
        with open(yol, encoding="utf-8") as f:
            veri = json.load(f)
        for no, sayfa in enumerate(veri.get("pdf_info", []), 1):
            for blok in sayfa.get("para_blocks", []) + sayfa.get("tables", []):
                if blok.get("type") in ("table", "table_body"):
                    mineru.add(no)

    docling_tablo = {t["sayfa"] for t in annot["tablolar"] if t["sayfa"]}
    return (mineru & docling_tablo,
            {o["sayfa"] for o in annot["ogeler"] if o["tur"] == "picture"},
            annot["tablolar"], annot["ogeler"])


def docling_sayfalari(stem: str) -> dict[int, str]:
    """Onceden uretilmis Docling sayfa markdown'i (docling_kos.py cikti).

    DIKKAT: bu metin TAM BELGE donusumunden geliyor. Uretimde yalniz secilen
    ardisik bloklar gonderiliyor; blok donusumunun ayni metni verdigi bu
    korpusta DOGRULANMADI.
    """
    yol = os.path.join(OUT, "docling_json", stem + "_sayfalar.json")
    if not os.path.exists(yol):
        return {}
    with open(yol, encoding="utf-8") as f:
        veri = json.load(f)
    return {i: metin for i, metin in enumerate(veri.get("sayfalar") or [], 1)}


def docling_belge_sn(stem: str) -> float | None:
    yol = os.path.join(OUT, "docling_sureler.json")
    if not os.path.exists(yol):
        return None
    with open(yol, encoding="utf-8") as f:
        veri = json.load(f)
    for b in veri.get("belgeler") or []:
        if b.get("belge") == stem:
            return b.get("sure_sn")
    return None


def _kutu(bbox: dict, yukseklik: float) -> list:
    """Docling bbox'ini sol-ust orijinli piksel kutusuna cevirir.

    TUZAK: tablo bbox'i BOTTOMLEFT, hucre bbox'i TOPLEFT orijinli geliyor.
    JSON her ikisinde de `orijin` alanini tasiyor, karari ona gore veriyoruz --
    tabani karistirmak kutuyu sayfanin ters ucuna koyar ve hata VERMEZ.
    """
    sol, sag = bbox["l"], bbox["r"]
    if bbox.get("orijin") == "BOTTOMLEFT":
        ust = yukseklik - max(bbox["t"], bbox["b"])
        alt = yukseklik - min(bbox["t"], bbox["b"])
    else:
        ust, alt = min(bbox["t"], bbox["b"]), max(bbox["t"], bbox["b"])
    return [round(sol * ZOOM, 1), round(ust * ZOOM, 1),
            round((sag - sol) * ZOOM, 1), round((alt - ust) * ZOOM, 1)]


def _hukum(ref: bool, kapi: bool) -> str:
    if ref and kapi:
        return "TP"
    if kapi:
        return "FP"
    return "FN" if ref else "TN"


def _yonlendirme(yol: str, ref_tablo: bool, ref_sekil: bool) -> str:
    """Sayfanin agir yola gitmesi gerekli miydi.

    OCR ayri tutulur: taranmis sayfada metin katmani yok, oraya gitmesi
    tartismasiz. GEREKLI/BOSA ayrimi referansta yapisal oge olup olmamasina
    bakar. KACIRILDI yalniz TABLO icin verilir -- Docling'in sekilli sayfada
    metne ne kattigi bu korpusta OLCULMEDI.
    """
    if yol == "OCR":
        return "OCR"
    if yol == "AGIR":
        return "GEREKLI" if (ref_tablo or ref_sekil) else "BOSA"
    return "KACIRILDI" if ref_tablo else "DOGRU_HIZLI"


def _kirp(metin: str) -> str:
    metin = metin or ""
    if len(metin) <= METIN_SINIR:
        return metin
    return metin[:METIN_SINIR] + "\n\n[... %d karakter daha, arayuzde kirpildi]" % (
        len(metin) - METIN_SINIR)


# --------------------------------------------------------------- toplama
def belge_topla(stem: str) -> dict:
    pdf_yolu = os.path.join(CORPUS, stem + ".pdf")
    tablo_sayfa, sekil_sayfa, tablolar, ogeler = referans(stem)
    heavy_metin = docling_sayfalari(stem)
    heavy_sn = docling_belge_sn(stem)

    # Sure oynakligi kendi basina bir bulguydu; tek kosuya guvenme, medyan al.
    sureler = []
    karar = None
    for _ in range(KOSU):
        basladi = time.perf_counter()
        karar = SmartRouterHatti().calistir(pdf_yolu, metin_dahil=True)
        sureler.append((time.perf_counter() - basladi) * 1000)
    toplam_ms = statistics.median(sureler)

    fast_metin = {int(n): t for n, t in karar["sayfa_metni"].items()}
    agir_sayfalar = [s["sayfa_no"] for s in karar["sayfalar"] if s["yol"] != "HIZLI"]
    kararlar = {s["sayfa_no"]: s.get("karar_kaynagi") or [] for s in karar["sayfalar"]}

    # Uretimdeki birlestirme AYNEN kullaniliyor; karantina/fallback kararlarini
    # burada yeniden yazmak, olculen davranistan sapma riski demek olurdu.
    puanla = SmartPdfParser()._page_scorer()
    sonuc = EngineResult(
        engine="docling",
        pages={n: heavy_metin.get(n, "") for n in agir_sayfalar if heavy_metin.get(n)},
        ok=bool(heavy_metin), mode="onceden-uretilmis-sayfa-cache",
    )
    basladi = time.perf_counter()
    birlesik = birlestir(fast_metin, decisions=kararlar, results=[sonuc],
                         requested={"docling": agir_sayfalar}, score=puanla)
    merge_ms = (time.perf_counter() - basladi) * 1000
    secilen = {p.page_no: p for p in birlesik.pages}

    os.makedirs(os.path.join(GORSEL, stem), exist_ok=True)
    belge = pymupdf.open(pdf_yolu)
    matris = pymupdf.Matrix(ZOOM, ZOOM)

    sayfalar = []
    for kayit in karar["sayfalar"]:
        no = kayit["sayfa_no"]
        sayfa = belge[no - 1]
        yukseklik = sayfa.rect.height
        goruntu = os.path.join(GORSEL, stem, "p%d.jpg" % no)
        if not os.path.exists(goruntu):
            sayfa.get_pixmap(matrix=matris).save(goruntu, jpg_quality=62)

        ref_t, ref_s = no in tablo_sayfa, no in sekil_sayfa
        f_metin, h_metin = fast_metin.get(no, ""), heavy_metin.get(no, "")
        f_puan = puanla(f_metin) if f_metin.strip() else None
        h_puan = puanla(h_metin) if h_metin.strip() else None
        birlesik_sayfa = secilen.get(no)

        kutular = [
            {"tur": "tablo", "kutu": _kutu(t["bbox"], yukseklik),
             "satir": t["satir"], "sutun": t["sutun"],
             "hucreler": [h["metin"] for h in t["hucreler"][:80]]}
            for t in tablolar if t["sayfa"] == no
        ] + [
            {"tur": "sekil", "kutu": _kutu(o["bbox"], yukseklik)}
            for o in ogeler if o["tur"] == "picture" and o["sayfa"] == no
        ]

        sayfalar.append({
            "sayfa_no": no,
            "gorsel": "hata_gorsel/%s/p%d.jpg" % (stem, no),
            "genislik": round(sayfa.rect.width * ZOOM),
            "yukseklik": round(yukseklik * ZOOM),
            "ref_tablo": ref_t, "ref_sekil": ref_s,
            "kapi_tablo": bool(kayit["has_table"]), "kapi_sekil": bool(kayit["has_figure"]),
            "tablo_guven": kayit.get("tablo_guven"),
            "needs_ocr": bool(kayit["needs_ocr"]),
            "yol": kayit["yol"], "motor": kayit["islenecek_motor"],
            "gerekce": kayit.get("karar_kaynagi") or [],
            "kalite": kayit.get("quality_score"),
            "kritik": kayit.get("critical_issue"),
            "sinyaller": kayit.get("gate_signals") or {},
            "kutular": kutular,
            "tablo_hukmu": _hukum(ref_t, bool(kayit["has_table"])),
            "sekil_hukmu": _hukum(ref_s, bool(kayit["has_figure"])),
            "yonlendirme": _yonlendirme(kayit["yol"], ref_t, ref_s),
            # --- metinler ve secim
            "fast_metin": _kirp(f_metin), "heavy_metin": _kirp(h_metin),
            "secilen_metin": _kirp(birlesik_sayfa.text if birlesik_sayfa else f_metin),
            "secilen_motor": birlesik_sayfa.engine if birlesik_sayfa else "pdf-inspector",
            "fast_karakter": len(f_metin), "heavy_karakter": len(h_metin),
            "fast_puan": None if f_puan is None else round(f_puan, 2),
            "heavy_puan": None if h_puan is None else round(h_puan, 2),
            # 2026-08-20: tolerans artik 0.1 (config/smart_router.yaml) ama
            # 3 ondalik kaldi -- karar_gerekcesi zaten esik uzerinden gecen
            # gercek nedeni yaziyor, bu alan yalniz ham farki gostermeye devam
            # ediyor.
            "puan_farki": (None if (f_puan is None or h_puan is None)
                           else round(h_puan - f_puan, 3)),
            # birlestir()'in _karar_ver'den dondurdugu insan-okur gerekce
            # (orn. "skor_farki_red (-0.220)", "heavy_formul_cozulemedi").
            # Sayfa hic agir motora gitmediyse None.
            "karar_gerekcesi": birlesik_sayfa.karar_gerekcesi if birlesik_sayfa else None,
            "karantina": no in birlesik.quarantined_pages,
            "fallback": no in birlesik.fallback_pages,
        })
    belge.close()

    n = len(sayfalar)
    agir = [s for s in sayfalar if s["yol"] != "HIZLI"]
    bosa = [s for s in sayfalar if s["yonlendirme"] == "BOSA"]
    kacan = [s for s in sayfalar if s["yonlendirme"] == "KACIRILDI"]
    heavy_ms_sayfa = None if heavy_sn is None else round(heavy_sn * 1000 / max(n, 1), 1)
    return {
        "belge": stem, "sayfa_sayisi": n, "sayfalar": sayfalar,
        "belge_skoru": karar["belge"]["quality_score"],
        "sureler_ms": karar["sureler_ms"], "ms_sayfa": karar["ms_sayfa"],
        "merge_ms": round(merge_ms, 1),
        "toplam_ms": round(toplam_ms, 1),
        "toplam_ms_sayfa": round(toplam_ms / max(n, 1), 2),
        "heavy_belge_sn": heavy_sn, "heavy_ms_sayfa": heavy_ms_sayfa,
        "agir_sayfa": len(agir), "bosa_sayfa": len(bosa), "kacan_sayfa": len(kacan),
        "karantina_sayfa": len(birlesik.quarantined_pages),
        "fallback_sayfa": len(birlesik.fallback_pages),
        "agir_sn": None if heavy_ms_sayfa is None else round(len(agir) * heavy_ms_sayfa / 1000, 1),
        "bosa_sn": None if heavy_ms_sayfa is None else round(len(bosa) * heavy_ms_sayfa / 1000, 1),
        "tam_belge_sn": heavy_sn,
    }


# --------------------------------------------------------------- sayfa uret
SABLON = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sayfa sayfa yonlendirme incelemesi</title><style>
:root{--bg:#f6f7f9;--kart:#fff;--metin:#1c1f23;--soluk:#6b7280;--cizgi:#e3e6ea;
--vurgu:#b4451f;--vurgu-bg:#fdf4f0;--uyari:#8a5a00;--uyari-bg:#fff8e6;--kod-bg:#f2f3f5;
--tp:#2e7d32;--tp-bg:#e9f5ea;--fp:#b8860b;--fp-bg:#fff6e0;--fn:#c0392b;--fn-bg:#fdecea;
--tablo:#2e7d32;--sekil:#1f6feb}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#14171a;--kart:#1c2024;--metin:#e6e8ea;--soluk:#9aa3ad;--cizgi:#2c3238;
--vurgu:#ff9f7a;--vurgu-bg:#2a1d17;--uyari:#e8c37a;--uyari-bg:#2a2312;--kod-bg:#24282d;
--tp:#8fbf8f;--tp-bg:#1b2a1c;--fp:#e8c37a;--fp-bg:#2a2312;--fn:#ff8a7a;--fn-bg:#2a1a18;
--tablo:#8fbf8f;--sekil:#79b8ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--metin);
font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif}
.ust{position:sticky;top:0;z-index:20;background:var(--kart);
border-bottom:1px solid var(--cizgi);padding:10px 18px}
.ust h1{margin:0 0 3px;font-size:17px}
.kucuk{color:var(--soluk);font-size:13px;font-weight:400}
.aciklama{color:var(--soluk);font-size:13px;margin:6px 0 10px;max-width:980px}
.aciklama b{color:var(--metin)}
.filtre{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.filtre select,.filtre button{font:inherit;font-size:13.5px;padding:5px 12px;
border:1px solid var(--cizgi);background:transparent;color:var(--metin);
border-radius:8px;cursor:pointer}
.filtre button:hover{border-color:var(--vurgu);color:var(--vurgu)}
.filtre button.aktif{background:var(--vurgu);color:#fff;border-color:var(--vurgu)}
.sayac{margin-left:auto;color:var(--soluk);font-size:13px}
.pano{margin:14px 18px;display:grid;
grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.kutucuk{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;
padding:12px 14px}
.kutucuk .sayi{font-size:23px;font-weight:700;line-height:1.15;
font-variant-numeric:tabular-nums}
.kutucuk .etiket{color:var(--soluk);font-size:12.5px;margin-top:2px}
.kutucuk.fp .sayi{color:var(--fp)}.kutucuk.fn .sayi{color:var(--fn)}
.kutucuk.tp .sayi{color:var(--tp)}
.uyari-kutu{margin:0 18px 14px;padding:12px 16px;background:var(--uyari-bg);
border:1px solid var(--uyari);border-radius:10px;font-size:13.5px}
.uyari-kutu ul{margin:6px 0 0;padding-left:20px}.uyari-kutu li{margin:4px 0}
.tablo-sar{margin:0 18px 16px;overflow-x:auto}
table.ozet{border-collapse:collapse;font-size:12.5px;min-width:1050px;width:100%;
background:var(--kart);border:1px solid var(--cizgi)}
table.ozet th,table.ozet td{border:1px solid var(--cizgi);padding:6px 9px;
text-align:right;white-space:nowrap}
table.ozet th{background:var(--kod-bg);font-weight:600;color:var(--soluk)}
table.ozet td:first-child,table.ozet th:first-child{text-align:left}
table.ozet tr:last-child{font-weight:700;background:var(--kod-bg)}
main{padding:0 18px 24px;display:flex;flex-direction:column;gap:14px}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;
padding:14px;display:grid;grid-template-columns:minmax(210px,290px) 1fr;gap:18px}
.kart.gizli{display:none}
.sahne{position:relative;width:100%;overflow:hidden;cursor:zoom-in}
.sahne img{width:100%;display:block;border:1px solid var(--cizgi);border-radius:6px}
.katman{position:absolute;left:0;top:0;transform-origin:0 0;pointer-events:none}
.kutu{position:absolute;border:2px solid;border-radius:2px}
.kutu.tablo{border-color:var(--tablo);background:rgba(46,125,50,.12)}
.kutu.sekil{border-color:var(--sekil);background:rgba(31,111,235,.10)}
.baslik{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;font-weight:700;
font-size:16px;margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid var(--vurgu)}
.rozetler{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.rz{font-size:12px;padding:3px 10px;border-radius:20px;border:1px solid var(--cizgi);
background:var(--kod-bg);color:var(--soluk)}
.rz.tp{background:var(--tp-bg);color:var(--tp);border-color:var(--tp)}
.rz.fp{background:var(--fp-bg);color:var(--fp);border-color:var(--fp)}
.rz.fn{background:var(--fn-bg);color:var(--fn);border-color:var(--fn)}
.rz.vurgulu{background:var(--vurgu-bg);color:var(--vurgu);border-color:var(--vurgu)}
table.veri{border-collapse:collapse;font-size:12.5px;width:100%}
table.veri th,table.veri td{border:1px solid var(--cizgi);padding:4px 8px;text-align:left}
table.veri th{background:var(--kod-bg);font-weight:600;width:165px;color:var(--soluk)}
.sekme{display:flex;gap:4px;margin:10px 0 0;flex-wrap:wrap}
.sekme button{font:inherit;font-size:12.5px;padding:4px 12px;border-radius:8px 8px 0 0;
border:1px solid var(--cizgi);border-bottom:0;background:var(--kod-bg);
color:var(--soluk);cursor:pointer}
.sekme button.aktif{background:var(--kart);color:var(--vurgu);font-weight:600}
pre.metin{margin:0;border:1px solid var(--cizgi);border-radius:0 8px 8px 8px;
background:var(--kod-bg);padding:11px;max-height:340px;overflow:auto;
white-space:pre-wrap;word-break:break-word;
font:12px/1.6 ui-monospace,Consolas,monospace}
details{margin-top:9px}
summary{cursor:pointer;color:var(--vurgu);font-size:12.5px}
.hucreler{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px}
.hucre{font-size:11.5px;background:var(--kod-bg);border:1px solid var(--cizgi);
border-radius:4px;padding:2px 6px;max-width:260px;overflow:hidden;
text-overflow:ellipsis;white-space:nowrap}
.sinyal{color:var(--soluk);margin-top:8px;
font:12px/1.6 ui-monospace,Consolas,monospace;word-break:break-word}
.buyutec{display:none;position:fixed;inset:0;z-index:100;background:rgba(8,10,12,.94);
flex-direction:column}
.buyutec.acik{display:flex}
.bt-cubuk{display:flex;align-items:center;gap:10px;padding:10px 16px;
background:var(--kart);border-bottom:1px solid var(--cizgi);flex-wrap:wrap}
#bt-baslik{font-weight:600;margin-right:auto}
#bt-oran{min-width:56px;text-align:center;color:var(--soluk);
font-variant-numeric:tabular-nums}
.bt-cubuk button{border:1px solid var(--cizgi);background:transparent;color:var(--metin);
padding:5px 13px;border-radius:7px;cursor:pointer;font-size:14px}
.bt-cubuk button:hover{border-color:var(--vurgu);color:var(--vurgu)}
#bt-kapat{border-color:var(--vurgu);color:var(--vurgu)}
.bt-alan{flex:1;overflow:auto;display:flex;align-items:flex-start;
justify-content:center;padding:16px}
#bt-sahne{position:relative;transform-origin:top center;background:#fff;
box-shadow:0 6px 40px rgba(0,0,0,.6)}
#bt-sahne img{display:block}
.bt-ipucu{padding:8px 16px;text-align:center;color:var(--soluk);font-size:12.5px;
background:var(--kart);border-top:1px solid var(--cizgi)}
@media(max-width:900px){.kart{grid-template-columns:1fr}}
</style></head><body>
<div class="ust">
  <h1>Sayfa sayfa yonlendirme incelemesi
    <span class="kucuk">&mdash; 9 belge, __N__ sayfa (v1)</span></h1>
  <p class="aciklama">Yesil kutu = referansta <b>tablo</b>, mavi kutu = referansta
  <b>sekil</b>. <b>TP/FP/FN</b> kapinin referansla anlasip anlasmadigini,
  <b>BOSA</b> sayfanin agir motora bosuna gittigini (referansta ne tablo ne sekil),
  <b>KACIRILDI</b> referansta tablo oldugu halde hizli yolda kaldigini gosterir.
  Metin sekmelerinde <b>fast</b> (pdf-inspector), <b>heavy</b> (Docling) ve
  <b>secilen</b> (uretimdeki merge sonucu) yan yana durur. Referans <b>gumus</b>
  &mdash; elle dogrulanmadi. Bu korpusun metin referansi olmadigi icin burada
  <b>utility/dogruluk puani yoktur</b>; "puan" sutunu critic'in bozulma skorudur.</p>
  <div class="filtre">
    <select id="belge"><option value="">Butun belgeler</option>__SECENEK__</select>
    <button data-f="hepsi" class="aktif">Hepsi</button>
    <button data-f="bosa">Bosa gonderilen</button>
    <button data-f="kacan">Kacirilan</button>
    <button data-f="karantina">Karantina</button>
    <button data-f="heavy-kotu">Heavy daha kotu</button>
    <button data-f="heavy-iyi">Heavy belirgin iyi</button>
    <button data-f="tablo-fp">Tablo FP</button>
    <button data-f="tablo-fn">Tablo FN</button>
    <button data-f="sekil-fp">Sekil FP</button>
    <button data-f="agir">Agir yol</button>
    <button data-f="ocr">OCR</button>
    <span class="sayac" id="sayac"></span>
  </div>
</div>
<div class="pano">__PANO__</div>
<div class="uyari-kutu">__NOTLAR__</div>
<div class="tablo-sar">__OZET_TABLO__</div>
<main id="liste"></main>
<div class="buyutec" id="bt">
  <div class="bt-cubuk">
    <span id="bt-baslik"></span>
    <button data-z="-">&minus;</button><span id="bt-oran">100%</span>
    <button data-z="+">+</button><button data-z="0">Sigdir</button>
    <button id="bt-kapat">Kapat (Esc)</button>
  </div>
  <div class="bt-alan"><div id="bt-sahne"><img id="bt-img" alt=""><div id="bt-kat"></div></div></div>
  <p class="bt-ipucu">Kutular referans tablo/sekil bolgeleridir.</p>
</div>
<script>
var VERI = __VERI__;
var liste = document.getElementById('liste');
var sayac = document.getElementById('sayac');
var filtre = 'hepsi', belgeSecim = '';

function kacis(s){
  return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function kutuHtml(s){
  return s.kutular.map(function(k){
    return '<div class="kutu ' + k.tur + '" style="left:' + k.kutu[0] + 'px;top:'
      + k.kutu[1] + 'px;width:' + k.kutu[2] + 'px;height:' + k.kutu[3] + 'px"></div>';
  }).join('');
}
function hucreBlok(s){
  var t = s.kutular.filter(function(k){ return k.tur === 'tablo'; });
  if(!t.length) return '';
  return t.map(function(k, i){
    var h = k.hucreler.map(function(x){
      return '<span class="hucre" title="' + kacis(x) + '">' + (kacis(x) || '&nbsp;') + '</span>';
    }).join('');
    return '<details><summary>Docling tablo ' + (i + 1) + ': ' + k.satir + '×'
      + k.sutun + ' &mdash; ilk ' + k.hucreler.length + ' hucre</summary>'
      + '<div class="hucreler">' + h + '</div></details>';
  }).join('');
}
function sinyalMetni(s){
  var g = s.sinyaller || {}, alan = ['ortogonal_cizgi','dolu_dikdortgen','izgara_sutun',
    'izgara_satir','kume_kaplama','gorsel_kaplama','bezier_egri','karakter'], c = [];
  for(var i = 0; i < alan.length; i++) if(alan[i] in g) c.push(alan[i] + '=' + g[alan[i]]);
  return c.join('   ');
}
function yonRozet(s){
  var m = {BOSA:['fp','BOSA GONDERILDI'], KACIRILDI:['fn','KACIRILDI'],
           GEREKLI:['tp','gerekli agir'], OCR:['vurgulu','OCR'],
           DOGRU_HIZLI:['','dogru hizli']};
  var r = m[s.yonlendirme];
  return '<span class="rz ' + r[0] + '">' + r[1] + '</span>';
}
function puanHtml(s){
  if(s.puan_farki === null)
    return '<span class="rz">puan karsilastirilamadi</span>';
  var sinif = s.puan_farki < 0 ? 'fn' : (s.puan_farki > 0 ? 'tp' : '');
  return '<span class="rz ' + sinif + '">critic puan fast ' + s.fast_puan
    + ' &rarr; heavy ' + s.heavy_puan + ' (' + (s.puan_farki > 0 ? '+' : '')
    + s.puan_farki + ')</span>';
}
function metinSekme(id, s){
  var t = [['fast','fast — pdf-inspector', s.fast_metin, s.fast_karakter],
           ['heavy','heavy — Docling', s.heavy_metin, s.heavy_karakter],
           ['secilen','secilen — ' + s.secilen_motor, s.secilen_metin, null]];
  var dug = t.map(function(x, i){
    return '<button data-t="' + id + '-' + x[0] + '"' + (i === 0 ? ' class="aktif"' : '')
      + '>' + x[1] + (x[3] === null ? '' : ' (' + x[3] + ' krk)') + '</button>';
  }).join('');
  var pre = t.map(function(x, i){
    return '<pre class="metin" id="' + id + '-' + x[0] + '"'
      + (i === 0 ? '' : ' style="display:none"') + '>'
      + (kacis(x[2]) || '<i>bu motor bu sayfa icin metin uretmedi</i>') + '</pre>';
  }).join('');
  return '<div class="sekme" data-grup="' + id + '">' + dug + '</div>' + pre;
}
function kart(b, s){
  var id = b + '-' + s.sayfa_no;
  return '<article class="kart" data-tablo="' + s.tablo_hukmu + '" data-sekil="'
    + s.sekil_hukmu + '" data-yol="' + s.yol + '" data-yon="' + s.yonlendirme
    + '" data-kar="' + (s.karantina ? '1' : '0') + '" data-fark="'
    + (s.puan_farki === null ? '' : s.puan_farki) + '">'
    + '<div><div class="sahne" data-belge="' + b + '" data-no="' + s.sayfa_no
    + '" style="aspect-ratio:' + s.genislik + '/' + s.yukseklik + '">'
    + '<img loading="lazy" src="' + s.gorsel + '" alt="' + b + ' sayfa ' + s.sayfa_no + '">'
    + '<div class="katman" data-w="' + s.genislik + '" style="width:' + s.genislik
    + 'px;height:' + s.yukseklik + 'px">' + kutuHtml(s) + '</div></div></div>'
    + '<div><div class="baslik">' + b + ' &mdash; sayfa ' + s.sayfa_no
    + '<span class="kucuk">' + s.yol + ' &rarr; ' + s.motor + ' &nbsp;|&nbsp; secilen: '
    + s.secilen_motor + '</span></div>'
    + '<div class="rozetler">' + yonRozet(s)
    + '<span class="rz ' + s.tablo_hukmu.toLowerCase() + '">tablo ' + s.tablo_hukmu + '</span>'
    + '<span class="rz ' + s.sekil_hukmu.toLowerCase() + '">sekil ' + s.sekil_hukmu + '</span>'
    + puanHtml(s)
    + (s.karantina ? '<span class="rz fn">KARANTINA</span>' : '')
    + (s.fallback ? '<span class="rz fp">FALLBACK</span>' : '')
    + (s.needs_ocr ? '<span class="rz fn">needs_ocr</span>' : '')
    + (s.karar_gerekcesi ? '<span class="rz" title="_karar_ver gerekcesi">karar: '
       + s.karar_gerekcesi + '</span>' : '')
    + (s.tablo_guven ? '<span class="rz">tablo guven: ' + s.tablo_guven + '</span>' : '')
    + (s.kritik && s.kritik !== 'NONE' ? '<span class="rz fp">' + s.kritik + '</span>' : '')
    + '</div><table class="veri">'
    + '<tr><th>Referans</th><td>tablo <b>' + (s.ref_tablo ? 'VAR' : 'yok')
    + '</b> &nbsp;&middot;&nbsp; sekil <b>' + (s.ref_sekil ? 'VAR' : 'yok') + '</b></td></tr>'
    + '<tr><th>Kapi ne dedi</th><td>has_table <b>' + s.kapi_tablo
    + '</b> &nbsp;&middot;&nbsp; has_figure <b>' + s.kapi_sekil + '</b></td></tr>'
    + '<tr><th>Karar nedeni</th><td>'
    + (s.gerekce.length ? s.gerekce.join(', ') : '&mdash;') + '</td></tr>'
    + '<tr><th>Kalite skoru (kapi)</th><td>'
    + (s.kalite === null ? 'olculemedi' : s.kalite) + '</td></tr></table>'
    + '<div class="sinyal">' + sinyalMetni(s) + '</div>'
    + metinSekme(id, s) + hucreBlok(s) + '</div></article>';
}
function ciz(){
  var p = [];
  for(var i = 0; i < VERI.length; i++){
    if(belgeSecim && VERI[i].belge !== belgeSecim) continue;
    for(var j = 0; j < VERI[i].sayfalar.length; j++)
      p.push(kart(VERI[i].belge, VERI[i].sayfalar[j]));
  }
  liste.innerHTML = p.join('');
  olcekle(); uygula();
}
function olcekle(){
  // Kutular tam cozunurluk pikselinde duruyor; goruntu kucultulunce ayni oranda kucult.
  var sahne = liste.querySelectorAll('.sahne');
  for(var i = 0; i < sahne.length; i++){
    var kat = sahne[i].querySelector('.katman');
    kat.style.transform = 'scale(' + (sahne[i].clientWidth / Number(kat.dataset.w)) + ')';
  }
}
function uygula(){
  var n = 0, k = liste.querySelectorAll('.kart');
  for(var i = 0; i < k.length; i++){
    var d = k[i].dataset, f = d.fark === '' ? null : Number(d.fark);
    var gor = filtre === 'hepsi'
      || (filtre === 'bosa' && d.yon === 'BOSA')
      || (filtre === 'kacan' && d.yon === 'KACIRILDI')
      || (filtre === 'karantina' && d.kar === '1')
      || (filtre === 'heavy-kotu' && f !== null && f < 0)
      || (filtre === 'heavy-iyi' && f !== null && f >= 5)
      || (filtre === 'tablo-fp' && d.tablo === 'FP')
      || (filtre === 'tablo-fn' && d.tablo === 'FN')
      || (filtre === 'sekil-fp' && d.sekil === 'FP')
      || (filtre === 'agir' && d.yol === 'AGIR')
      || (filtre === 'ocr' && d.yol === 'OCR');
    k[i].className = gor ? 'kart' : 'kart gizli';
    if(gor) n++;
  }
  sayac.textContent = n + ' sayfa gosteriliyor';
}
var dugme = document.querySelectorAll('[data-f]');
for(var d = 0; d < dugme.length; d++) dugme[d].onclick = (function(el){
  return function(){
    for(var x = 0; x < dugme.length; x++) dugme[x].className = '';
    el.className = 'aktif'; filtre = el.dataset.f; uygula();
  };
})(dugme[d]);
document.getElementById('belge').onchange = function(e){ belgeSecim = e.target.value; ciz(); };
addEventListener('resize', olcekle);

/* metin sekmeleri + buyutec */
var bt = document.getElementById('bt'), btImg = document.getElementById('bt-img'),
    btKat = document.getElementById('bt-kat'), btSahne = document.getElementById('bt-sahne'),
    btOran = document.getElementById('bt-oran'), oran = 1;
function btUygula(){
  btSahne.style.transform = 'scale(' + oran + ')';
  btOran.textContent = Math.round(oran * 100) + '%';
}
liste.onclick = function(e){
  var sek = e.target.closest ? e.target.closest('[data-t]') : null;
  if(sek){
    var grup = sek.parentNode;
    var dugmeler = grup.querySelectorAll('[data-t]');
    for(var i = 0; i < dugmeler.length; i++){
      dugmeler[i].className = '';
      document.getElementById(dugmeler[i].dataset.t).style.display = 'none';
    }
    sek.className = 'aktif';
    document.getElementById(sek.dataset.t).style.display = 'block';
    return;
  }
  var sahne = e.target.closest ? e.target.closest('.sahne') : null;
  if(!sahne) return;
  var b = sahne.dataset.belge, no = Number(sahne.dataset.no), kayit = null;
  for(var i = 0; i < VERI.length; i++) if(VERI[i].belge === b)
    for(var j = 0; j < VERI[i].sayfalar.length; j++)
      if(VERI[i].sayfalar[j].sayfa_no === no) kayit = VERI[i].sayfalar[j];
  if(!kayit) return;
  document.getElementById('bt-baslik').textContent = b + ' — sayfa ' + no;
  btImg.src = kayit.gorsel; btImg.width = kayit.genislik; btImg.height = kayit.yukseklik;
  btSahne.style.width = kayit.genislik + 'px'; btSahne.style.height = kayit.yukseklik + 'px';
  btKat.style.cssText = 'position:absolute;left:0;top:0;width:' + kayit.genislik
    + 'px;height:' + kayit.yukseklik + 'px';
  btKat.innerHTML = kutuHtml(kayit);
  oran = 1; btUygula(); bt.className = 'buyutec acik';
};
var zoomlar = document.querySelectorAll('[data-z]');
for(var q = 0; q < zoomlar.length; q++) zoomlar[q].onclick = (function(el){
  return function(){
    var v = el.dataset.z;
    oran = v === '+' ? Math.min(oran * 1.25, 6)
         : v === '-' ? Math.max(oran / 1.25, 0.2) : 1;
    btUygula();
  };
})(zoomlar[q]);
document.getElementById('bt-kapat').onclick = function(){ bt.className = 'buyutec'; };
addEventListener('keydown', function(e){ if(e.key === 'Escape') bt.className = 'buyutec'; });
ciz();
</script></body></html>
"""


def _kutucuk(sayi, etiket: str, sinif: str = "") -> str:
    return ('<div class="kutucuk %s"><div class="sayi">%s</div>'
            '<div class="etiket">%s</div></div>' % (sinif, sayi, etiket))


def pano_html(veriler: list[dict]) -> str:
    sayfalar = [s for b in veriler for s in b["sayfalar"]]
    n = len(sayfalar)
    agir = sum(1 for s in sayfalar if s["yol"] != "HIZLI")
    bosa = sum(1 for s in sayfalar if s["yonlendirme"] == "BOSA")
    kacan = sum(1 for s in sayfalar if s["yonlendirme"] == "KACIRILDI")
    karan = sum(1 for s in sayfalar if s["karantina"])
    kotu = sum(1 for s in sayfalar if (s["puan_farki"] or 0) < 0)
    kapi_ms = sum(b["sureler_ms"]["kapi_ms"] for b in veriler)
    hat_ms = sum(b["toplam_ms"] for b in veriler)
    heavy_sn = sum(b["heavy_belge_sn"] or 0 for b in veriler)
    kurtarilan = sum(
        (b["sayfa_sayisi"] - b["agir_sayfa"]) * (b["heavy_ms_sayfa"] or 0) / 1000
        for b in veriler)
    return "".join([
        _kutucuk(n, "toplam sayfa"),
        _kutucuk("%d <span style='font-size:14px'>(%%%d)</span>"
                 % (agir, round(100 * agir / n)), "agir yola giden"),
        _kutucuk("%d <span style='font-size:14px'>(%%%d)</span>"
                 % (bosa, round(100 * bosa / max(agir, 1))),
                 "BOSA giden — agir sayfanin orani", "fp"),
        _kutucuk(kacan, "KACIRILAN tablo sayfasi", "fn"),
        _kutucuk(karan, "karantinaya alinan heavy sayfa", "fn"),
        _kutucuk(kotu, "heavy critic puani daha dusuk", "fp"),
        _kutucuk("%.2f ms" % (kapi_ms / n), "kapi / sayfa (olculdu)"),
        _kutucuk("%.1f ms" % (hat_ms / n), "tum hizli hat / sayfa (olculdu)"),
        _kutucuk("%.0f sn" % heavy_sn, "Docling tam belge toplami (olculdu)"),
        _kutucuk("%.0f sn" % kurtarilan, "agir motordan kurtarilan (amortize)", "tp"),
    ])


def ozet_tablo(veriler: list[dict]) -> str:
    bas = ("<table class='ozet'><tr><th>Belge</th><th>Sayfa</th><th>Agir</th>"
           "<th>BOSA</th><th>KACIRILAN</th><th>Karantina</th><th>Fallback</th>"
           "<th>Tablo TP/FP/FN</th><th>Sekil TP/FP/FN</th>"
           "<th>inspector ms</th><th>kapi ms</th><th>critic ms</th><th>merge ms</th>"
           "<th>hizli hat ms/sayfa</th><th>Docling belge sn</th>"
           "<th>Docling ms/sayfa</th><th>BOSA sn</th></tr>")
    satir = []
    top = dict(n=0, agir=0, bosa=0, kacan=0, kar=0, fb=0, bosa_sn=0.0, heavy_sn=0.0)
    for b in veriler:
        s = b["sayfalar"]

        def say(alan, hukum, kume=s):
            return sum(1 for x in kume if x[alan] == hukum)

        satir.append(
            "<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td>"
            "<td>%d</td><td>%d / %d / %d</td><td>%d / %d / %d</td>"
            "<td>%.0f</td><td>%.0f</td><td>%.0f</td><td>%.1f</td><td>%.1f</td>"
            "<td>%s</td><td>%s</td><td>%s</td></tr>"
            % (b["belge"], b["sayfa_sayisi"], b["agir_sayfa"], b["bosa_sayfa"],
               b["kacan_sayfa"], b["karantina_sayfa"], b["fallback_sayfa"],
               say("tablo_hukmu", "TP"), say("tablo_hukmu", "FP"), say("tablo_hukmu", "FN"),
               say("sekil_hukmu", "TP"), say("sekil_hukmu", "FP"), say("sekil_hukmu", "FN"),
               b["sureler_ms"]["inspector_ms"], b["sureler_ms"]["kapi_ms"],
               b["sureler_ms"]["critic_ms"], b["merge_ms"], b["toplam_ms_sayfa"],
               "—" if b["heavy_belge_sn"] is None else "%.1f" % b["heavy_belge_sn"],
               "—" if b["heavy_ms_sayfa"] is None else "%.0f" % b["heavy_ms_sayfa"],
               "—" if b["bosa_sn"] is None else "%.1f" % b["bosa_sn"]))
        top["n"] += b["sayfa_sayisi"]; top["agir"] += b["agir_sayfa"]
        top["bosa"] += b["bosa_sayfa"]; top["kacan"] += b["kacan_sayfa"]
        top["kar"] += b["karantina_sayfa"]; top["fb"] += b["fallback_sayfa"]
        top["bosa_sn"] += b["bosa_sn"] or 0
        top["heavy_sn"] += b["heavy_belge_sn"] or 0

    tum = [x for b in veriler for x in b["sayfalar"]]

    def hepsi(alan, hukum):
        return sum(1 for x in tum if x[alan] == hukum)

    hat = sum(b["toplam_ms"] for b in veriler)
    satir.append(
        "<tr><td>TOPLAM</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td>"
        "<td>%d</td><td>%d / %d / %d</td><td>%d / %d / %d</td>"
        "<td>%.0f</td><td>%.0f</td><td>%.0f</td><td>%.1f</td><td>%.1f</td>"
        "<td>%.1f</td><td>%.0f</td><td>%.1f</td></tr>"
        % (top["n"], top["agir"], top["bosa"], top["kacan"], top["kar"], top["fb"],
           hepsi("tablo_hukmu", "TP"), hepsi("tablo_hukmu", "FP"), hepsi("tablo_hukmu", "FN"),
           hepsi("sekil_hukmu", "TP"), hepsi("sekil_hukmu", "FP"), hepsi("sekil_hukmu", "FN"),
           sum(b["sureler_ms"]["inspector_ms"] for b in veriler),
           sum(b["sureler_ms"]["kapi_ms"] for b in veriler),
           sum(b["sureler_ms"]["critic_ms"] for b in veriler),
           sum(b["merge_ms"] for b in veriler), hat / top["n"],
           top["heavy_sn"], top["heavy_sn"] * 1000 / top["n"], top["bosa_sn"]))
    return bas + "".join(satir) + "</table>"


NOTLAR = """<b>Sayilari okurken:</b>
<ul>
<li><b>Olculen:</b> inspector / kapi / critic / merge sureleri &mdash; %d kosunun
medyani, makine bosken. Docling belge sureleri onceki tam-belge kosusundan gelir.</li>
<li><b>Amortize (sayfa basina ayri olcum degil):</b> "Docling ms/sayfa" belgenin
toplam Docling suresinin sayfa sayisina bolumu. Uretimde yalniz secilen ardisik
bloklar gonderiliyor ve koprude ~5,2 sn/cagri baslangic maliyeti ayrica olculmustu;
gercek maliyet bu sayidan farkli olabilir.</li>
<li><b>Heavy metin tam belge donusumunden geliyor.</b> Uretim yalniz secilen
bloklari gonderiyor; blok donusumunun ayni metni verdigi bu korpusta
<b>dogrulanmadi</b>.</li>
<li><b>"critic puan" referansa gore dogruluk DEGIL.</b> Bozulmus karakter, tekrar,
kirik satir gibi motorlar arasi karsilastirilabilir bozulma sinyallerini olcer;
merge'in karantina karari da bu skora bakar. Formul anlami, yanlis kelime ve
okuma sirasi kaybini goremez.</li>
<li><b>KACIRILDI</b> yalniz <b>tablo</b> icin sayilir. Referansta sekil olup hizli
yolda kalan sayfa kacirilmis sayilmadi &mdash; Docling'in sekilli sayfada metne ne
kattigi bu korpusta <b>olculmedi</b>.</li>
<li>Referans <b>gumus</b>: tabloda MinerU ile Docling'in anlastigi sayfalar. Ikisi de
yanilirsa buradaki TP/FP/FN de yanilir; ornekleri gozle dogrulamak icin
"Bosa gonderilen" ve "Kacirilan" filtreleri var.</li>
</ul>""" % KOSU


def main() -> int:
    os.makedirs(GORSEL, exist_ok=True)
    veriler = []
    for stem in BELGELER:
        basladi = time.perf_counter()
        veriler.append(belge_topla(stem))
        b = veriler[-1]
        print("%-30s %3d sayfa | agir %3d | bosa %3d | kacan %2d | karantina %2d | %5.1f sn"
              % (stem, b["sayfa_sayisi"], b["agir_sayfa"], b["bosa_sayfa"],
                 b["kacan_sayfa"], b["karantina_sayfa"], time.perf_counter() - basladi),
              flush=True)

    n = sum(b["sayfa_sayisi"] for b in veriler)
    secenek = "".join('<option value="%s">%s</option>' % (b["belge"], b["belge"])
                      for b in veriler)
    sayfa = (SABLON
             .replace("__N__", str(n))
             .replace("__SECENEK__", secenek)
             .replace("__PANO__", pano_html(veriler))
             .replace("__NOTLAR__", NOTLAR)
             .replace("__OZET_TABLO__", ozet_tablo(veriler))
             .replace("__VERI__", json.dumps(veriler, ensure_ascii=False)))
    yol = os.path.join(HTML, "hata_arayuzu.html")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(sayfa)
    with open(os.path.join(OUT, "hata_arayuzu_veri.json"), "w", encoding="utf-8") as f:
        json.dump(veriler, f, ensure_ascii=False, indent=1)
    print("\n-> %s  (%.1f MB)" % (yol, os.path.getsize(yol) / 1e6))
    print("-> %s" % os.path.join(OUT, "hata_arayuzu_veri.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
