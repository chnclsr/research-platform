"""C1 replay sonuclarini belge belge gozle inceleme arayuzu.

`hata_arayuzu.py` kendi korpusumuzun 261 sayfasini gosterir ama o korpusun METIN
REFERANSI yoktur -- orada "Docling gercekten daha mi iyi cikardi" sorusu ancak
gozle cevaplanir. Bu arayuz tamamlayicisidir: C1 korpusunda metin referansi
VARDIR, yani yonlendirme kararinin dogru olup olmadigi olculebilir.

Her belge icin gosterilenler:

  * Yol karari: hangi sayfa hangi motora gitti, hangi gerekce ile.
  * Hukum: karar referansa gore dogru muydu (DOGRU HEAVY / BOSA HEAVY /
    KACIRILDI / dogru fast).
  * Karantina: hangi sayfa reddedildi, hangi gerekce ile, ve bu kararin
    utility maliyeti.
  * Uc metin: fast (pdf-inspector), heavy (Docling), secilen (merge).
  * Skorlar: utility / char_similarity / token_f1, ucu icin ayri ayri.
  * Sureler: bu makinede olculen fast+gate+critic+merge suresi.

IKI KOSU KARSILASTIRMASI: --kiyas ile ikinci bir run verilirse, route karari
degisen belgeler ayrica isaretlenir ve panoda iki kosunun metrikleri yan yana
gosterilir.

NE OLCMEZ: heavy motor bu replay'lerde cache'ten okunur, yani Docling'in
gercek suresi ve `smart_pdf._run_heavy_pages` orkestrasyonu bu arayuzde YOKTUR.
Cache duration_ms alani baska bir makinenin olcumudur, oldugu gibi isaretlenir.

Kullanim
--------
    .venv311\\Scripts\\python.exe scripts\\c1_arayuz.py \\
        --run dangling_geri_alma_v6_20260821 \\
        --kiyas yeniden_gate_replay_v4_20260820
    -> html/c1_arayuz.html
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KOSULAR = os.path.join(BASE, "out", "c1_runs")
HTML = os.path.join(BASE, "html")
GORSEL = os.path.join(HTML, "c1_gorsel")
VARSAYILAN_MANIFEST = os.path.join(BASE, "out", "korpus_envanteri.jsonl")

#: Sayfa goruntusu buyutme carpani. hata_arayuzu.py ile ayni: 1.5 ~ 108 dpi.
ZOOM = 1.5

#: Sayfa goruntuleri JPEG olarak yazilir; 201 sayfa PNG olsaydi ~30 MB tutardi.
JPEG_KALITE = 78

#: Arayuze gomulen metin siniri. Uzun belgelerde dosya sismesin diye kirpilir;
#: kirpildigi metnin sonunda acikca yazilir.
METIN_SINIR = 5000

#: Referans "heavy gercekten daha iyiydi" esigi -- c1_dogrulama.py ile ayni.
FAYDA_ESIK = 0.02


def _oku(run: str) -> dict:
    """predictions.jsonl -> {kimlik: satir}. Resume tekrarlarinda sonuncusu gecerli."""
    yol = os.path.join(KOSULAR, run, "predictions.jsonl")
    if not os.path.isfile(yol):
        raise SystemExit("kosu bulunamadi: %s" % yol)
    son = {}
    with open(yol, encoding="utf-8") as f:
        for satir in f:
            if satir.strip():
                kayit = json.loads(satir)
                if kayit.get("id"):
                    son[kayit["id"]] = kayit
    return son


def _metin(run: str, tur: str, kimlik: str) -> str:
    yol = os.path.join(KOSULAR, run, "markdown", tur, kimlik + ".md")
    if not os.path.isfile(yol):
        return ""
    with open(yol, encoding="utf-8") as f:
        t = f.read()
    if len(t) > METIN_SINIR:
        return t[:METIN_SINIR] + "\n\n… [%d karakter kirpildi]" % (len(t) - METIN_SINIR)
    return t


def _manifest(yol: str) -> dict:
    """kimlik -> manifest kaydi. PDF yolunu cozmek icin gerekiyor."""
    if not os.path.isfile(yol):
        return {}
    kayitlar = {}
    with open(yol, encoding="utf-8") as f:
        for s in f:
            if s.strip():
                r = json.loads(s)
                if r.get("kimlik"):
                    kayitlar[r["kimlik"]] = r
    return kayitlar


def _pdf_yolu(kayit: dict) -> str | None:
    """Manifest'teki goreli yolu mutlak yola cevirir -- c1_dogrulama._coz ile ayni kural."""
    goreli = kayit.get("pdf_yolu")
    if not goreli:
        return None
    from korpus_kaynak import KORPUS_KOK  # noqa: PLC0415  -- yalniz gorsel uretirken
    kok = BASE if kayit.get("yol_koku") == "staj" else KORPUS_KOK
    yol = os.path.join(kok, *goreli.split("/"))
    return yol if os.path.isfile(yol) else None


def gorsel_uret(kimlikler: list[str], manifest: dict) -> dict:
    """Her belgenin sayfalarini JPEG'e cevirir; {kimlik: {sayfa_no: goreli_yol}}.

    PyMuPDF yoksa ya da PDF bulunamazsa sessizce bos doner -- arayuz gorselsiz
    de calisir, yalniz "sayfa goruntusu yok" yazar.
    """
    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError:
            print("PyMuPDF yok, sayfa goruntuleri uretilmedi")
            return {}

    os.makedirs(GORSEL, exist_ok=True)
    matris = pymupdf.Matrix(ZOOM, ZOOM)
    sonuc: dict = {}
    uretilen = atlanan = 0
    for kimlik in kimlikler:
        kayit = manifest.get(kimlik)
        if not kayit:
            atlanan += 1
            continue
        yol = _pdf_yolu(kayit)
        if not yol:
            atlanan += 1
            continue
        try:
            belge = pymupdf.open(yol)
        except Exception:
            atlanan += 1
            continue
        try:
            sayfalar = {}
            for i in range(belge.page_count):
                ad = "%s_s%d.jpg" % (kimlik.replace("/", "_"), i + 1)
                hedef = os.path.join(GORSEL, ad)
                if not os.path.isfile(hedef):
                    pix = belge.load_page(i).get_pixmap(matrix=matris)
                    pix.save(hedef, jpg_quality=JPEG_KALITE)
                    uretilen += 1
                sayfalar[i + 1] = "c1_gorsel/" + ad
            if sayfalar:
                sonuc[kimlik] = sayfalar
        except Exception:
            atlanan += 1
        finally:
            belge.close()
    print("sayfa goruntusu: %d belge (%d yeni kare, %d belge atlandi)"
          % (len(sonuc), uretilen, atlanan))
    return sonuc


def _hukum(routed: bool, fayda: float) -> str:
    """Gate karari referansa gore dogru muydu."""
    if routed:
        return "dogru_heavy" if fayda >= FAYDA_ESIK else "bosa_heavy"
    return "kacirildi" if fayda >= FAYDA_ESIK else "dogru_fast"


def _toplu(kayitlar: list[dict]) -> dict:
    """Bir kosunun belge-duzeyi metrikleri. c1_dogrulama._ozet ile ayni tanimlar."""
    routed = [r for r in kayitlar if r["route"]["routed_heavy"]]
    kazanan = [r for r in kayitlar if r["delta"]["heavy_minus_fast"] >= FAYDA_ESIK]
    dogru = [r for r in routed if r["delta"]["heavy_minus_fast"] >= FAYDA_ESIK]
    toplam_fayda = sum(max(r["delta"]["heavy_minus_fast"], 0.0) for r in kayitlar)
    alinan = sum(max(r["delta"]["routed_minus_fast"], 0.0) for r in kayitlar)
    return {
        "belge": len(kayitlar),
        "routed": len(routed),
        "referans_kazanan": len(kazanan),
        "precision": (len(dogru) / len(routed)) if routed else None,
        "recall": (len(dogru) / len(kazanan)) if kazanan else None,
        "yakalanan": (alinan / toplam_fayda) if toplam_fayda else None,
        "fast_u": sum(r["scores"]["fast"]["utility"] for r in kayitlar) / len(kayitlar),
        "heavy_u": sum(r["scores"]["heavy"]["utility"] for r in kayitlar) / len(kayitlar),
        "routed_u": sum(r["scores"]["routed"]["utility"] for r in kayitlar) / len(kayitlar),
        "karantinali": len([r for r in kayitlar if r["merge"]["quarantined_pages"]]),
        # Karantinanin kacirdigi fayda: heavy iyiydi ama merge reddetti.
        "karantina_maliyeti": sum(
            max(r["delta"]["heavy_minus_fast"] - r["delta"]["routed_minus_fast"], 0.0)
            for r in kayitlar if r["merge"]["quarantined_pages"]),
    }


def _parmak_izi(kayitlar: dict) -> set[str]:
    """Kosunun hangi metrik ortaminda uretildigi. Eski kosularda alan yok."""
    return {r["scores"]["fast"].get("metric_fingerprint", "bilinmiyor")
            for r in kayitlar.values() if r.get("status") == "ok"}


def veri_hazirla(run: str, kiyas: str | None, gorseller: dict | None = None) -> dict:
    gorseller = gorseller or {}
    ana = _oku(run)
    esk = _oku(kiyas) if kiyas else {}

    # Farkli algoritmayla olculmus iki kosuyu yan yana koymak, parser
    # davranisi degismemisken utility farki uydurur (rapor Bolum O.1).
    uyari = None
    if esk:
        a, b = _parmak_izi(ana), _parmak_izi(esk)
        if a != b and "bilinmiyor" not in (a | b):
            uyari = ("UYARI: iki kosu farkli metrik ortaminda uretilmis (%s vs %s) "
                     "-- utility farklari karsilastirilabilir DEGIL."
                     % (", ".join(sorted(a)), ", ".join(sorted(b))))
            print(uyari)
    kimlikler = sorted(k for k, r in ana.items() if r.get("status") == "ok")
    if esk:
        kimlikler = [k for k in kimlikler if esk.get(k, {}).get("status") == "ok"]

    belgeler = []
    for kimlik in kimlikler:
        b = ana[kimlik]
        a = esk.get(kimlik)
        fayda = b["delta"]["heavy_minus_fast"]
        elde = b["delta"]["routed_minus_fast"]
        karantina = b["merge"]["quarantined_pages"] or []

        belge_gorsel = gorseller.get(kimlik, {})
        sayfalar = []
        for s in b["route"]["pages"]:
            gerekce = s.get("karar_kaynagi") or []
            no = s.get("sayfa_no")
            sayfalar.append({
                "no": no,
                "motor": "docling" if gerekce else "pdf-inspector",
                "gerekce": gerekce,
                "kalite": s.get("kalite_skoru"),
                # Skoru hangi ceza dusurdu -- eski kosularda bu alan yok.
                "cezalar": s.get("kalite_cezalari") or {},
                "karantina": no in karantina,
                "gorsel": belge_gorsel.get(no) or belge_gorsel.get(str(no)),
            })

        kayit = {
            "id": kimlik,
            "ds": b["dataset"],
            "hukum": _hukum(b["route"]["routed_heavy"], fayda),
            "routed": b["route"]["routed_heavy"],
            "fayda": round(fayda, 4),
            "elde": round(elde, 4),
            # Karantina bu belgede ne kadar fayda yuttu.
            "karantina_maliyeti": round(max(fayda - elde, 0.0), 4) if karantina else 0.0,
            "u": {ad: round(b["scores"][ad]["utility"], 4) for ad in ("fast", "heavy", "routed")},
            "char": {ad: round(b["scores"][ad]["char_similarity"], 4) for ad in ("fast", "heavy", "routed")},
            "tf1": {ad: round(b["scores"][ad]["token_f1"], 4) for ad in ("fast", "heavy", "routed")},
            "karantina": karantina,
            "degraded": b["merge"]["degraded"],
            "notlar": b["merge"]["notes"],
            "sure_ms": round(b["duration_ms"], 1),
            "cache_ms": round(b["engine"]["duration_ms"], 1),
            "sayfalar": sayfalar,
            "md": {t: _metin(run, t, kimlik) for t in ("fast", "heavy", "routed")},
        }
        if a:
            kayit["eski_routed"] = a["route"]["routed_heavy"]
            kayit["eski_elde"] = round(a["delta"]["routed_minus_fast"], 4)
            kayit["degisti"] = a["route"]["routed_heavy"] != b["route"]["routed_heavy"]
            kayit["fark"] = round(elde - a["delta"]["routed_minus_fast"], 4)
        else:
            kayit["degisti"] = False
            kayit["fark"] = 0.0
        belgeler.append(kayit)

    sureler = [b["sure_ms"] for b in belgeler]
    liste = [ana[k] for k in kimlikler]
    return {
        "run": run,
        "kiyas": kiyas,
        "metrik_uyarisi": uyari,
        "parmak_izi": sorted(_parmak_izi(ana)),
        "esik_version": liste[0]["route"]["threshold_version"] if liste else "",
        "motor": ana[kimlikler[0]]["engine"]["detail"] if kimlikler else "",
        "toplam_manifest": len(ana),
        "ozet": _toplu(liste),
        "eski_ozet": _toplu([esk[k] for k in kimlikler]) if esk else None,
        "sure": {
            "medyan": round(st.median(sureler), 1),
            "ortalama": round(st.mean(sureler), 1),
            "p90": round(sorted(sureler)[int(len(sureler) * 0.9)], 1),
            "max": round(max(sureler), 1),
        },
        "belgeler": belgeler,
    }


SABLON = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>C1 yonlendirme incelemesi</title><style>
:root{--bg:#f6f7f9;--kart:#fff;--metin:#1c1f23;--soluk:#6b7280;--cizgi:#e3e6ea;
--vurgu:#b4451f;--vurgu-bg:#fdf4f0;--uyari:#8a5a00;--uyari-bg:#fff8e6;--kod-bg:#f2f3f5;
--tp:#2e7d32;--tp-bg:#e9f5ea;--fp:#b8860b;--fp-bg:#fff6e0;--fn:#c0392b;--fn-bg:#fdecea;
--agir:#1f6feb;--agir-bg:#eaf2fd}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#14171a;--kart:#1c2024;--metin:#e6e8ea;--soluk:#9aa3ad;--cizgi:#2c3238;
--vurgu:#ff9f7a;--vurgu-bg:#2a1d17;--uyari:#e8c37a;--uyari-bg:#2a2312;--kod-bg:#24282d;
--tp:#8fbf8f;--tp-bg:#1b2a1c;--fp:#e8c37a;--fp-bg:#2a2312;--fn:#ff8a7a;--fn-bg:#2a1a18;
--agir:#79b8ff;--agir-bg:#16232f}}
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
.filtre input,.filtre button{font:inherit;font-size:13.5px;padding:5px 12px;
border:1px solid var(--cizgi);background:transparent;color:var(--metin);
border-radius:8px}
.filtre button{cursor:pointer}
.filtre input{min-width:150px}
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
.kutucuk .onceki{color:var(--soluk);font-size:12px;margin-top:4px;
font-variant-numeric:tabular-nums}
.kutucuk .onceki b{font-weight:600}
.iyi{color:var(--tp)}.kotu{color:var(--fn)}.notr{color:var(--soluk)}
.kutucuk.fp .sayi{color:var(--fp)}.kutucuk.fn .sayi{color:var(--fn)}
.kutucuk.tp .sayi{color:var(--tp)}
.uyari-kutu{margin:0 18px 14px;padding:12px 16px;background:var(--uyari-bg);
border:1px solid var(--uyari);border-radius:10px;font-size:13.5px}
.uyari-kutu.kirmizi{background:var(--fn-bg);border-color:var(--fn)}
.uyari-kutu h3{margin:0 0 5px;font-size:14px}
.uyari-kutu p{margin:0 0 6px}
.uyari-kutu p:last-child{margin-bottom:0}
.sarmal{display:grid;grid-template-columns:minmax(240px,320px) 1fr;gap:14px;
margin:0 18px 40px;align-items:start}
@media(max-width:900px){.sarmal{grid-template-columns:1fr}}
.kart{background:var(--kart);border:1px solid var(--cizgi);border-radius:10px;
overflow:hidden}
.liste{max-height:620px;overflow-y:auto}
.satir{display:block;width:100%;text-align:left;border:0;border-bottom:1px solid var(--cizgi);
background:transparent;color:var(--metin);padding:9px 12px;cursor:pointer;font:inherit}
.satir:hover{background:var(--kod-bg)}
.satir.secili{background:var(--vurgu-bg);box-shadow:inset 3px 0 0 var(--vurgu)}
.satir .bas{display:flex;justify-content:space-between;gap:8px;align-items:center}
.satir .kim{font-size:13px;font-weight:600;font-variant-numeric:tabular-nums}
.satir .alt{color:var(--soluk);font-size:12px;margin-top:3px;display:flex;gap:9px;
flex-wrap:wrap;font-variant-numeric:tabular-nums}
.rz{display:inline-block;font-size:11px;padding:1px 7px;border-radius:6px;
border:1px solid var(--cizgi);background:var(--kod-bg);color:var(--soluk);
white-space:nowrap;font-weight:600}
.rz.tp{background:var(--tp-bg);color:var(--tp);border-color:var(--tp)}
.rz.fp{background:var(--fp-bg);color:var(--fp);border-color:var(--fp)}
.rz.fn{background:var(--fn-bg);color:var(--fn);border-color:var(--fn)}
.rz.agir{background:var(--agir-bg);color:var(--agir);border-color:var(--agir)}
.rz.vurgulu{background:var(--vurgu-bg);color:var(--vurgu);border-color:var(--vurgu)}
.detay-bas{padding:13px 16px;border-bottom:1px solid var(--cizgi)}
.detay-bas h2{margin:0;font-size:16px;font-variant-numeric:tabular-nums}
.etiketler{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.skorlar{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
gap:1px;background:var(--cizgi);border-bottom:1px solid var(--cizgi)}
.skor{background:var(--kart);padding:10px 14px}
.skor.secili{background:var(--vurgu-bg)}
.skor .etiket{color:var(--soluk);font-size:12px}
.skor .sayi{font-size:18px;font-weight:700;margin-top:2px;
font-variant-numeric:tabular-nums}
.skor .ek{color:var(--soluk);font-size:11.5px;margin-top:2px;
font-variant-numeric:tabular-nums}
.blok{padding:13px 16px;border-bottom:1px solid var(--cizgi)}
.blok:last-child{border-bottom:0}
.blok h3{margin:0 0 8px;font-size:13px;color:var(--soluk);font-weight:600}
.kaydir{overflow-x:auto}
table.veri{border-collapse:collapse;width:100%;font-size:13px}
table.veri th,table.veri td{padding:6px 10px;border-bottom:1px solid var(--cizgi);
text-align:left;white-space:nowrap}
table.veri th{background:var(--kod-bg);font-weight:600;color:var(--soluk);font-size:12px}
table.veri td.n,table.veri th.n{text-align:right;font-variant-numeric:tabular-nums}
table.veri tr:last-child td{border-bottom:0}
.sekme{display:flex;gap:4px;margin-bottom:8px;flex-wrap:wrap}
.sekme button{font:inherit;font-size:12.5px;padding:4px 11px;border:1px solid var(--cizgi);
background:var(--kod-bg);color:var(--soluk);border-radius:8px;cursor:pointer}
.sekme button.aktif{background:var(--kart);color:var(--vurgu);font-weight:600;
border-color:var(--vurgu)}
pre.metin{margin:0;background:var(--kod-bg);padding:11px;max-height:380px;overflow:auto;
border:1px solid var(--cizgi);border-radius:8px;font:12px/1.6 ui-monospace,Consolas,monospace;
white-space:pre-wrap;word-break:break-word}
.bos{padding:50px 16px;text-align:center;color:var(--soluk)}
.dip{color:var(--soluk);font-size:12.5px;margin:6px 0 0;font-variant-numeric:tabular-nums}
.sayfalar{display:flex;gap:12px;flex-wrap:wrap}
.sayfa-kart{border:1px solid var(--cizgi);border-radius:8px;overflow:hidden;
background:var(--kod-bg);max-width:340px}
.sayfa-kart.reddedildi{border-color:var(--fn);box-shadow:0 0 0 1px var(--fn)}
.sayfa-kart.agirda{border-color:var(--agir)}
.sayfa-kart img{display:block;width:100%;height:auto;cursor:zoom-in;background:#fff}
.sayfa-kart .bilgi{padding:6px 9px;font-size:12px;background:var(--kart);
border-top:1px solid var(--cizgi);display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.sayfa-yok{padding:14px;color:var(--soluk);font-size:12.5px}
.buyutec{display:none;position:fixed;inset:0;z-index:100;background:rgba(8,10,12,.94);
overflow:auto;padding:16px;text-align:center}
.buyutec.acik{display:block}
.buyutec img{max-width:none;background:#fff;border-radius:4px}
.buyutec .kapat{position:fixed;top:14px;right:18px;font:inherit;font-size:14px;
padding:6px 14px;border:1px solid #555;background:#1c2024;color:#e6e8ea;
border-radius:8px;cursor:pointer;z-index:101}
.buyutec .basligi{position:fixed;top:16px;left:18px;color:#e6e8ea;font-size:13px;z-index:101}
</style></head><body>

<div class="ust">
  <h1>C1 yonlendirme incelemesi <span class="kucuk" id="kunye"></span></h1>
  <p class="aciklama">Metin referansli C1 korpusunda her belgenin yol karari, karantina
  sonucu ve uc motorun ciktisi. <b>Heavy motor bu kosuda cache'ten okundu</b> — Docling'in
  gercek suresi ve <code>smart_pdf._run_heavy_pages</code> orkestrasyonu burada olculmedi.</p>
  <div class="filtre" id="filtre">
    <input type="search" id="ara" placeholder="kimlik ara…">
    <button data-f="hepsi" class="aktif">hepsi</button>
    <button data-f="degisti">route degisti</button>
    <button data-f="karantina">karantina</button>
    <button data-f="bosa">bosa heavy</button>
    <button data-f="kacirildi">kacirildi</button>
    <button data-f="heavy">heavy'e giden</button>
    <span class="sayac" id="sayac"></span>
  </div>
</div>

<div id="bulgular"></div>
<div class="pano" id="pano"></div>
<div id="ablation"></div>

<div class="sarmal">
  <div class="kart">
    <div class="liste" id="liste"></div>
  </div>
  <div class="kart" id="detay"><div class="bos">Soldan bir belge sec.</div></div>
</div>

<div class="buyutec" id="buyutec">
  <span class="basligi" id="bt-baslik"></span>
  <button class="kapat" id="bt-kapat" type="button">kapat (Esc)</button>
  <img id="bt-resim" alt="">
</div>

<script id="veri" type="application/json">__VERI__</script>
<script>
const D = JSON.parse(document.getElementById("veri").textContent);
const $ = (s) => document.querySelector(s);
const yap = (t, c, x) => { const n = document.createElement(t);
  if (c) n.className = c; if (x !== undefined) n.textContent = x; return n; };
const f4 = (v) => (v === null || v === undefined) ? "—" : Number(v).toFixed(4);
const im = (v) => (v > 0 ? "+" : "") + Number(v).toFixed(4);

const HUKUM = {
  dogru_heavy: ["tp", "DOGRU HEAVY"], dogru_fast: ["", "dogru fast"],
  bosa_heavy:  ["fp", "BOSA HEAVY"],  kacirildi:  ["fn", "KACIRILDI"],
};

$("#kunye").textContent = "· " + D.ozet.belge + " belge · " + D.run +
  (D.kiyas ? " (kiyas: " + D.kiyas + ")" : "") + " · " + D.esik_version;

/* ---------------------------------------------------------------- bulgular */
const degisen = D.belgeler.filter(b => b.degisti);
const netFark = degisen.reduce((s, b) => s + b.fark, 0);
const kazanc  = degisen.filter(b => b.fark > 0.005);
const kayip   = degisen.filter(b => b.fark < -0.005);
const bloke   = D.belgeler.filter(b => b.karantina_maliyeti > 0.005);

function kutu(sinif, baslik, ...paragraflar) {
  const d = yap("div", "uyari-kutu" + (sinif ? " " + sinif : ""));
  d.appendChild(yap("h3", null, baslik));
  paragraflar.forEach(p => d.appendChild(yap("p", null, p)));
  return d;
}
const bl = $("#bulgular");
if (D.metrik_uyarisi) {
  bl.appendChild(kutu("kirmizi", "Metrik ortami uyusmuyor", D.metrik_uyarisi));
}
if (D.kiyas && degisen.length) {
  bl.appendChild(kutu(netFark < -0.005 ? "kirmizi" : "",
    "Route karari " + degisen.length + " belgede degisti — net etki " + im(netFark),
    kazanc.length + " belge kazandi, " + kayip.length + " belge kaybetti, " +
    (degisen.length - kazanc.length - kayip.length) + " notr. " +
    "Net etki, yakalanan-fayda oranindan farkli isaret verebilir: o metrik yalniz " +
    "pozitif deltalari toplar, gereksiz heavy cagrisinin zararini saymaz."));
}
if (bloke.length) {
  bl.appendChild(kutu("",
    "Karantina " + bloke.length + " belgede fayda yutuyor — toplam " +
    D.ozet.karantina_maliyeti.toFixed(4),
    "Bu belgelerde heavy referansa gore daha iyiydi ve sayfa heavy'e gonderildi, " +
    "ama merge karantinasi reddettigi icin elde kalan fayda sifir: " +
    bloke.slice(0, 8).map(b => b.id + " (" + im(b.fayda) + ")").join(", ") +
    (bloke.length > 8 ? " …" : "") + "."));
}

/* ------------------------------------------------------------------- pano */
const ALANLAR = [
  ["routed", "heavy'e giden belge", 0, 1],
  ["precision", "route precision", 4, 1],
  ["recall", "route recall", 4, 1],
  ["yakalanan", "yakalanan fayda orani", 4, 1],
  ["routed_u", "routed utility (ort.)", 4, 1],
  ["karantinali", "karantinali belge", 0, -1],
  ["karantina_maliyeti", "karantinanin yuttugu fayda", 4, -1],
];
const pano = $("#pano");
ALANLAR.forEach(([anahtar, etiket, basamak, yon]) => {
  const yeni = D.ozet[anahtar], eski = D.eski_ozet ? D.eski_ozet[anahtar] : null;
  const k = yap("div", "kutucuk");
  k.appendChild(yap("div", "sayi", basamak ? Number(yeni).toFixed(basamak) : String(yeni)));
  k.appendChild(yap("div", "etiket", etiket));
  if (eski !== null && eski !== undefined) {
    const d = yeni - eski;
    const sinif = Math.abs(d) < 1e-9 ? "notr" : (d * yon > 0 ? "iyi" : "kotu");
    const p = yap("div", "onceki");
    p.innerHTML = "kiyas: " + (basamak ? Number(eski).toFixed(basamak) : eski) +
      " <b class='" + sinif + "'>" + (d > 0 ? "+" : "") +
      (basamak ? d.toFixed(basamak) : d) + "</b>";
    k.appendChild(p);
  }
  pano.appendChild(k);
});
{
  const k = yap("div", "kutucuk");
  k.appendChild(yap("div", "sayi", D.sure.medyan.toFixed(0)));
  k.appendChild(yap("div", "etiket", "ms · medyan (fast+gate+critic+merge)"));
  k.appendChild(yap("div", "onceki", "p90 " + D.sure.p90.toFixed(0) +
    " · en yavas " + D.sure.max.toFixed(0) + " ms"));
  pano.appendChild(k);
}

/* --------------------------------------------------------------- ablation */
if (D.ablation) {
  const A = D.ablation;
  const kap = $("#ablation");
  const bas = yap("div", "uyari-kutu");
  bas.appendChild(yap("h3", null,
    "Dunku degisikliklerin tek tek etkisi (leave-one-out, " + A.belge + " belge)"));
  bas.appendChild(yap("p", null,
    "Her satir, o degisikligi TEK BASINA dun-oncesi degerine dondurup tam sistemi " +
    "yeniden kosmanin sonucu. Δ'lar bugunku sisteme goredir; pozitif ΔNET, o " +
    "degisikligi GERI ALMANIN daha iyi oldugu anlamina gelir."));
  bas.appendChild(yap("p", null,
    "NET = toplam(routed_utility - fast_utility). `yakalanan fayda orani`ndan farki: " +
    "o metrik yalniz pozitif deltalari sayar, gereksiz heavy cagrisinin zararini " +
    "gormezden gelir — bu yuzden tek basina esik secmek icin kullanilamaz."));
  const kaydir = yap("div", "kaydir");
  const t = document.createElement("table");
  t.className = "veri";
  t.style.marginTop = "10px";
  t.innerHTML = "<thead><tr><th>geri alinan degisiklik</th><th class='n'>heavy</th>" +
    "<th class='n'>precision</th><th class='n'>recall</th><th class='n'>karantina</th>" +
    "<th class='n'>NET</th><th class='n'>ΔNET</th><th>hukum</th></tr></thead>";
  const gvd = document.createElement("tbody");
  const satir = (ad, m, dnet, hukum, kalin) => {
    const tr = document.createElement("tr");
    if (kalin) tr.style.fontWeight = "700";
    tr.appendChild(yap("td", null, ad));
    tr.appendChild(yap("td", "n", String(m.routed)));
    tr.appendChild(yap("td", "n", m.precision.toFixed(4)));
    tr.appendChild(yap("td", "n", m.recall.toFixed(4)));
    tr.appendChild(yap("td", "n", m.karantinali + " (" + m.karantina_maliyeti.toFixed(3) + ")"));
    tr.appendChild(yap("td", "n", m.net.toFixed(4)));
    tr.appendChild(yap("td", "n", dnet === null ? "—" : im(dnet)));
    const h = yap("td");
    if (hukum) {
      const sinif = hukum === "zararli" ? "fn" : (hukum === "faydali" ? "tp" : "");
      const yazi = hukum === "zararli" ? "DEGISIKLIGI CIKAR"
                 : hukum === "faydali" ? "DEGISIKLIGI TUT" : "notr — C1'de etkisiz";
      h.appendChild(yap("span", "rz " + sinif, yazi));
    } else h.textContent = "—";
    tr.appendChild(h);
    return tr;
  };
  gvd.appendChild(satir("— bugunku sistem (taban)", A.taban, null, null, true));
  A.deneyler.forEach(d => gvd.appendChild(
    satir(d.aciklama, d.olcum, d.d_net, d.hukum, false)));
  t.appendChild(gvd); kaydir.appendChild(t); bas.appendChild(kaydir);
  kap.appendChild(bas);
}

/* ----------------------------------------------------------------- gezgin */
let suzgec = "hepsi", arama = "", secili = null;

function suzulmus() {
  return D.belgeler.filter(b => {
    if (arama && !b.id.toLowerCase().includes(arama)) return false;
    if (suzgec === "degisti")   return b.degisti;
    if (suzgec === "karantina") return b.karantina.length > 0;
    if (suzgec === "bosa")      return b.hukum === "bosa_heavy";
    if (suzgec === "kacirildi") return b.hukum === "kacirildi";
    if (suzgec === "heavy")     return b.routed;
    return true;
  });
}

function listeCiz() {
  const liste = $("#liste"); liste.innerHTML = "";
  const veri = suzulmus();
  $("#sayac").textContent = veri.length + " / " + D.belgeler.length + " belge";
  veri.forEach(b => {
    const s = yap("button", "satir" + (secili === b.id ? " secili" : ""));
    s.type = "button";
    const bas = yap("div", "bas");
    bas.appendChild(yap("span", "kim", b.id));
    bas.appendChild(yap("span", "rz " + HUKUM[b.hukum][0], HUKUM[b.hukum][1]));
    s.appendChild(bas);
    const alt = yap("div", "alt");
    alt.appendChild(yap("span", null, b.routed ? "heavy" : "fast"));
    alt.appendChild(yap("span", null, "u " + f4(b.u.routed)));
    if (b.karantina.length) alt.appendChild(yap("span", "kotu", "karantina"));
    if (b.degisti) alt.appendChild(yap("span", "vurgulu", "Δroute " + im(b.fark)));
    s.appendChild(alt);
    s.addEventListener("click", () => { secili = b.id; listeCiz(); detayCiz(b); });
    liste.appendChild(s);
  });
}

function detayCiz(b) {
  const d = $("#detay"); d.innerHTML = "";

  const bas = yap("div", "detay-bas");
  bas.appendChild(yap("h2", null, b.id));
  const et = yap("div", "etiketler");
  et.appendChild(yap("span", "rz", b.ds));
  et.appendChild(yap("span", "rz " + HUKUM[b.hukum][0], HUKUM[b.hukum][1]));
  et.appendChild(yap("span", "rz " + (b.routed ? "agir" : ""), b.routed ? "heavy'e gitti" : "fast kaldi"));
  if (b.degisti) et.appendChild(yap("span", "rz vurgulu",
    "ROUTE DEGISTI (kiyasta: " + (b.eski_routed ? "heavy" : "fast") + ")"));
  if (b.karantina.length) et.appendChild(yap("span", "rz fn",
    "KARANTINA s." + b.karantina.join(",")));
  if (b.degraded) et.appendChild(yap("span", "rz fp", "DEGRADED"));
  bas.appendChild(et);
  d.appendChild(bas);

  const sk = yap("div", "skorlar");
  [["fast", "fast"], ["heavy", "heavy"], ["routed", "secilen (routed)"]].forEach(([k, ad]) => {
    const s = yap("div", "skor" + (k === "routed" ? " secili" : ""));
    s.appendChild(yap("div", "etiket", ad + " utility"));
    s.appendChild(yap("div", "sayi", f4(b.u[k])));
    s.appendChild(yap("div", "ek", "char " + f4(b.char[k]) + " · f1 " + f4(b.tf1[k])));
    sk.appendChild(s);
  });
  const s4 = yap("div", "skor");
  s4.appendChild(yap("div", "etiket", "heavy fazlasi (referans)"));
  s4.appendChild(yap("div", "sayi", im(b.fayda)));
  s4.appendChild(yap("div", "ek", "elde kalan " + im(b.elde) +
    (b.karantina_maliyeti > 0 ? " · karantina yuttu " + b.karantina_maliyeti.toFixed(4) : "")));
  sk.appendChild(s4);
  d.appendChild(sk);

  const gb = yap("div", "blok");
  gb.appendChild(yap("h3", null, "sayfa goruntusu (orijinal PDF)"));
  const gkap = yap("div", "sayfalar");
  let gorselVar = false;
  b.sayfalar.forEach(s => {
    if (!s.gorsel) return;
    gorselVar = true;
    const k = yap("div", "sayfa-kart" +
      (s.karantina ? " reddedildi" : (s.motor === "docling" ? " agirda" : "")));
    const img = document.createElement("img");
    img.src = s.gorsel;
    img.alt = b.id + " sayfa " + s.no;
    img.loading = "lazy";
    img.addEventListener("click", () => buyut(s.gorsel,
      b.id + " · sayfa " + s.no + " · " + s.motor +
      (s.karantina ? " · KARANTINA" : "")));
    k.appendChild(img);
    const bilgi = yap("div", "bilgi");
    bilgi.appendChild(yap("span", null, "s." + s.no));
    bilgi.appendChild(yap("span", "rz " + (s.motor === "docling" ? "agir" : ""), s.motor));
    if (s.karantina) bilgi.appendChild(yap("span", "rz fn", "REDDEDILDI"));
    k.appendChild(bilgi);
    gkap.appendChild(k);
  });
  if (gorselVar) {
    gb.appendChild(gkap);
    gb.appendChild(yap("p", "dip", "goruntuye tiklayinca tam boyutta acilir"));
  } else {
    gb.appendChild(yap("div", "sayfa-yok",
      "Bu belge icin sayfa goruntusu uretilmedi (PDF bulunamadi ya da PyMuPDF yok)."));
  }
  d.appendChild(gb);

  const sb = yap("div", "blok");
  sb.appendChild(yap("h3", null, "sayfa kararlari"));
  const kaydir = yap("div", "kaydir");
  const t = document.createElement("table");
  t.className = "veri";
  t.innerHTML = "<thead><tr><th class='n'>sayfa</th><th>motor</th><th>karar gerekcesi</th>" +
    "<th class='n'>kalite</th><th>ceza dokumu</th><th>karantina</th></tr></thead>";
  const gvd = document.createElement("tbody");
  b.sayfalar.forEach(s => {
    const tr = document.createElement("tr");
    tr.appendChild(yap("td", "n", String(s.no)));
    const mt = yap("td");
    mt.appendChild(yap("span", "rz " + (s.motor === "docling" ? "agir" : ""), s.motor));
    tr.appendChild(mt);
    tr.appendChild(yap("td", null, s.gerekce.length ? s.gerekce.join(", ") : "—"));
    tr.appendChild(yap("td", "n", (s.kalite === null || s.kalite === undefined)
      ? "—" : Number(s.kalite).toFixed(1)));
    // Skoru hangi cezanin ne kadar dusurdugu; tek ceza varsa vurgulu gosterilir
    // -- 26 low_quality sayfasinin 25'inde o tek ceza dangling'di (rapor O.8.2).
    const ct = yap("td");
    const adlar = Object.keys(s.cezalar || {}).sort((x, y) => s.cezalar[y] - s.cezalar[x]);
    if (!adlar.length) ct.textContent = "—";
    else adlar.forEach(a => ct.appendChild(
      yap("span", "rz " + (adlar.length === 1 ? "fn" : "fp"),
          a + " −" + Number(s.cezalar[a]).toFixed(1))));
    tr.appendChild(ct);
    const qt = yap("td");
    if (s.karantina) qt.appendChild(yap("span", "rz fn", "REDDEDILDI"));
    else qt.textContent = "—";
    tr.appendChild(qt);
    gvd.appendChild(tr);
  });
  t.appendChild(gvd); kaydir.appendChild(t); sb.appendChild(kaydir);
  d.appendChild(sb);

  if (b.notlar.length) {
    const nb = yap("div", "blok");
    nb.appendChild(yap("h3", null, "birlestirme notlari"));
    nb.appendChild(yap("pre", "metin", b.notlar.join("\\n")));
    d.appendChild(nb);
  }

  const mb = yap("div", "blok");
  mb.appendChild(yap("h3", null, "cikti metni"));
  const sekme = yap("div", "sekme");
  const pre = yap("pre", "metin");
  let aktif = "routed";
  const ciz = () => {
    pre.textContent = b.md[aktif] || "(cikti yok)";
    [...sekme.children].forEach(c => c.classList.toggle("aktif", c.dataset.t === aktif));
  };
  ["fast", "heavy", "routed"].forEach(k => {
    const btn = yap("button", null, k + " (" + f4(b.u[k]) + ")");
    btn.type = "button"; btn.dataset.t = k;
    btn.addEventListener("click", () => { aktif = k; ciz(); });
    sekme.appendChild(btn);
  });
  mb.appendChild(sekme); mb.appendChild(pre); ciz();
  d.appendChild(mb);

  const zb = yap("div", "blok");
  zb.appendChild(yap("h3", null, "sure"));
  zb.appendChild(yap("p", "dip", "bu makinede olculen (fast + gate + critic + merge): " +
    b.sure_ms.toFixed(1) + " ms"));
  zb.appendChild(yap("p", "dip", "cache'teki heavy duration_ms (baska makinenin olcumu, " +
    "bu kosuda Docling calismadi): " + b.cache_ms.toFixed(1) + " ms"));
  d.appendChild(zb);
}

/* --------------------------------------------------------------- buyutec */
const BT = $("#buyutec");
function buyut(kaynak, baslik) {
  $("#bt-resim").src = kaynak;
  $("#bt-baslik").textContent = baslik;
  BT.classList.add("acik");
}
$("#bt-kapat").addEventListener("click", () => BT.classList.remove("acik"));
BT.addEventListener("click", e => { if (e.target === BT) BT.classList.remove("acik"); });
document.addEventListener("keydown", e => {
  if (e.key === "Escape") BT.classList.remove("acik");
});

document.querySelectorAll("#filtre button").forEach(b => b.addEventListener("click", () => {
  suzgec = b.dataset.f;
  document.querySelectorAll("#filtre button").forEach(o => o.classList.toggle("aktif", o === b));
  listeCiz();
}));
$("#ara").addEventListener("input", e => {
  arama = e.target.value.toLowerCase().trim(); listeCiz();
});
listeCiz();
</script></body></html>
"""


def main() -> int:
    p = argparse.ArgumentParser(description="C1 replay inceleme arayuzu")
    p.add_argument("--run", required=True, help="out/c1_runs altindaki kosu adi")
    p.add_argument("--kiyas", help="karsilastirilacak onceki kosu adi")
    p.add_argument("--ablation", help="c1_ablation.py ciktisi (ablation_ozet.json)")
    p.add_argument("--manifest", default=VARSAYILAN_MANIFEST,
                   help="sayfa goruntusu icin PDF yollarini cozer")
    p.add_argument("--gorselsiz", action="store_true",
                   help="sayfa goruntusu uretme (hizli yeniden uretim)")
    p.add_argument("--cikti", default=os.path.join(HTML, "c1_arayuz.html"))
    args = p.parse_args()

    gorseller = {}
    if not args.gorselsiz:
        sys.path.insert(0, os.path.join(BASE, "src"))
        manifest = _manifest(args.manifest)
        if manifest:
            kimlikler = sorted(k for k, r in _oku(args.run).items()
                               if r.get("status") == "ok")
            gorseller = gorsel_uret(kimlikler, manifest)
        else:
            print("manifest yok (%s), sayfa goruntusu uretilmedi" % args.manifest)

    veri = veri_hazirla(args.run, args.kiyas, gorseller)
    if args.ablation and os.path.isfile(args.ablation):
        with open(args.ablation, encoding="utf-8") as f:
            veri["ablation"] = json.load(f)
    # `</script>` dizisi gomulu JSON'u erken kapatmasin diye kacirilir.
    gomulu = json.dumps(veri, ensure_ascii=False).replace("<", "\\u003c")
    os.makedirs(os.path.dirname(args.cikti), exist_ok=True)
    with open(args.cikti, "w", encoding="utf-8", newline="") as f:
        f.write(SABLON.replace("__VERI__", gomulu))

    o = veri["ozet"]
    print("belge=%d routed=%d precision=%s recall=%s karantina=%d (maliyet %.4f)"
          % (o["belge"], o["routed"],
             ("%.4f" % o["precision"]) if o["precision"] is not None else "-",
             ("%.4f" % o["recall"]) if o["recall"] is not None else "-",
             o["karantinali"], o["karantina_maliyeti"]))
    print("yazildi: %s (%.2f MB)" % (args.cikti, os.path.getsize(args.cikti) / 1048576))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
